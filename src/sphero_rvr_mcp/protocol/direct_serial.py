"""Direct serial connection to RVR - bypasses SDK async overhead."""

import serial
import threading
import time
from typing import Optional
from . import commands
from .packet import parse_response, ParsedResponse


class DirectSerial:
    """Synchronous direct serial connection to RVR for low-latency commands."""

    def __init__(self, port: str = "/dev/ttyS0", baud: int = 115200):
        self._port = port
        self._baud = baud
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    def connect(self) -> bool:
        """Open serial connection."""
        with self._lock:
            if self._serial and self._serial.is_open:
                return True
            try:
                self._serial = serial.Serial(self._port, self._baud, timeout=0.1)
                return True
            except Exception:
                return False

    def disconnect(self):
        """Close serial connection."""
        with self._lock:
            if self._serial:
                self._serial.close()
                self._serial = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def _send(self, packet: bytes) -> bool:
        """Send packet (fire-and-forget)."""
        with self._lock:
            if not self._serial or not self._serial.is_open:
                return False
            try:
                self._serial.write(packet)
                self._serial.flush()
                return True
            except Exception:
                return False

    def _send_and_wait(self, packet: bytes, timeout: float = 1.0) -> Optional[ParsedResponse]:
        """Send packet and wait for response.

        Args:
            packet: Command packet to send
            timeout: Maximum time to wait for response (seconds)

        Returns:
            ParsedResponse if received, None on timeout or error
        """
        with self._lock:
            if not self._serial or not self._serial.is_open:
                return None

            try:
                # Flush any pending input
                self._serial.reset_input_buffer()

                # Send command
                self._serial.write(packet)
                self._serial.flush()

                # Read response
                start_time = time.time()
                buffer = bytearray()

                while time.time() - start_time < timeout:
                    if self._serial.in_waiting > 0:
                        byte = self._serial.read(1)
                        buffer.extend(byte)

                        # Check if we have a complete packet (SOP...EOP)
                        if len(buffer) >= 2 and buffer[-1] == 0xD8:  # EOP
                            try:
                                response = parse_response(bytes(buffer))
                                return response
                            except ValueError:
                                # Not a valid packet yet, keep reading
                                pass

                    # Small sleep to avoid busy-waiting
                    time.sleep(0.001)

                return None  # Timeout
            except Exception:
                return None

    # High-level commands

    def wake(self) -> bool:
        """Wake RVR from sleep."""
        return self._send(commands.wake())

    def reset_yaw(self) -> bool:
        """Reset yaw - set current heading as 0."""
        return self._send(commands.reset_yaw())

    def drive_with_heading(self, speed: int, heading: int, reverse: bool = False) -> bool:
        """Drive at speed toward heading."""
        flags = 1 if reverse else 0
        return self._send(commands.drive_with_heading(speed, heading, flags))

    def raw_motors(self, left_speed: int, right_speed: int) -> bool:
        """Direct motor control. Negative = reverse."""
        left_mode = 2 if left_speed < 0 else (1 if left_speed > 0 else 0)
        right_mode = 2 if right_speed < 0 else (1 if right_speed > 0 else 0)
        return self._send(commands.raw_motors(
            left_mode, abs(left_speed),
            right_mode, abs(right_speed)
        ))

    def stop(self) -> bool:
        """Stop the robot."""
        return self._send(commands.stop())

    def set_all_leds(self, r: int, g: int, b: int) -> bool:
        """Set all LEDs to RGB color."""
        return self._send(commands.set_all_leds(r, g, b))

    def set_led_group(self, group_name: str, r: int, g: int, b: int) -> bool:
        """Set a specific LED group to RGB color.

        Args:
            group_name: One of: headlight_left, headlight_right, battery_door_front,
                        battery_door_rear, power_button_front, power_button_rear,
                        brakelight_left, brakelight_right, status_indication_left,
                        status_indication_right
            r, g, b: Color values 0-255

        Returns:
            True if command sent successfully
        """
        try:
            packet = commands.set_led_group(group_name, r, g, b)
            return self._send(packet)
        except ValueError:
            return False

    def reset_locator(self) -> bool:
        """Reset locator X,Y position to origin."""
        return self._send(commands.reset_locator())

    def send_ir_message(self, code: int, strength: int = 32) -> bool:
        """Send IR message. Code: 0-7, Strength: 0-64."""
        return self._send(commands.send_ir_message(code, strength))

    def start_ir_broadcasting(self, far_code: int, near_code: int) -> bool:
        """Start IR broadcasting for robot-to-robot communication."""
        return self._send(commands.start_ir_broadcast(far_code, near_code))

    def stop_ir_broadcasting(self) -> bool:
        """Stop IR broadcasting."""
        return self._send(commands.stop_ir_broadcast())

    def enable_color_detection(self, enabled: bool = True, timeout: float = 1.0) -> bool:
        """Enable or disable color detection on bottom sensor (controls belly LED).

        Args:
            enabled: True to turn on belly LED, False to turn off
            timeout: Response timeout in seconds

        Returns:
            True if command acknowledged, False on timeout/error
        """
        packet = commands.enable_color_detection(enabled)
        response = self._send_and_wait(packet, timeout)
        return response is not None

    def drive_tank(self, left_velocity: float, right_velocity: float) -> bool:
        """Drive with tank controls (independent left/right velocities).

        Args:
            left_velocity: Left track velocity (-1.0 to 1.0)
            right_velocity: Right track velocity (-1.0 to 1.0)

        Returns:
            True if command sent successfully
        """
        # Convert float velocities (-1.0 to 1.0) to raw motor values (0-255)
        left_speed = int(abs(left_velocity) * 255)
        right_speed = int(abs(right_velocity) * 255)

        # Clamp to valid range
        left_speed = max(0, min(255, left_speed))
        right_speed = max(0, min(255, right_speed))

        # Determine motor modes: 0=off, 1=forward, 2=reverse
        left_mode = 0 if left_speed == 0 else (2 if left_velocity < 0 else 1)
        right_mode = 0 if right_speed == 0 else (2 if right_velocity < 0 else 1)

        return self._send(commands.raw_motors(left_mode, left_speed, right_mode, right_speed))

    def drive_rc(self, linear_velocity: float, yaw_velocity: float) -> bool:
        """Drive with RC-style controls.

        Args:
            linear_velocity: Forward/backward velocity (-1.0 to 1.0)
            yaw_velocity: Turn rate (-1.0 to 1.0, positive = turn right)

        Returns:
            True if command sent successfully
        """
        # Convert to tank-style controls
        # linear_velocity controls forward/backward
        # yaw_velocity controls differential between tracks

        # Mix: left = linear + yaw, right = linear - yaw
        left = linear_velocity + yaw_velocity
        right = linear_velocity - yaw_velocity

        # Normalize if either exceeds 1.0
        max_val = max(abs(left), abs(right))
        if max_val > 1.0:
            left /= max_val
            right /= max_val

        return self.drive_tank(left, right)

    # Query commands (with responses)

    def get_battery_percentage(self, timeout: float = 1.0) -> Optional[int]:
        """Get battery percentage (0-100).

        Returns:
            Battery percentage 0-100, or None on error
        """
        packet = commands.get_battery_percentage()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 1:
            return response.data[0]
        return None

    def get_rgbc_sensor_values(self, timeout: float = 1.0) -> Optional[dict]:
        """Get RGBC color sensor values.

        Returns:
            Dict with keys: 'red', 'green', 'blue', 'clear', or None on error
        """
        packet = commands.get_rgbc_sensor_values()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 8:
            import struct
            # Response is 4x uint16_t (big-endian)
            red, green, blue, clear = struct.unpack('>HHHH', response.data[:8])
            return {
                'red': red,
                'green': green,
                'blue': blue,
                'clear': clear
            }
        return None

    def get_current_detected_color(self, timeout: float = 1.0) -> Optional[dict]:
        """Get current detected color (triggers LED illumination).

        Returns:
            Dict with color info, or None on error
        """
        packet = commands.get_current_detected_color()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 5:
            # Response: red(u8), green(u8), blue(u8), confidence(u8), color_id(u8)
            red, green, blue, confidence, color_id = response.data[:5]
            return {
                'red': red,
                'green': green,
                'blue': blue,
                'confidence': confidence,
                'color_classification_id': color_id
            }
        return None

    def get_ambient_light(self, timeout: float = 1.0) -> Optional[float]:
        """Get ambient light sensor value.

        Returns:
            Ambient light value (float), or None on error
        """
        packet = commands.get_ambient_light()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 4:
            import struct
            # Response is float32 (big-endian)
            light_value = struct.unpack('>f', response.data[:4])[0]
            return light_value
        return None

    # Distance-based movement using RVR's internal position controller

    def drive_to_position_si(self, yaw_angle: float, x: float, y: float,
                              linear_speed: float = 0.5, flags: int = 0) -> bool:
        """Drive to position using SI units (meters).

        Uses RVR's internal position controller for accurate movement.

        Args:
            yaw_angle: Target heading in degrees
            x: Target X in meters (positive = right)
            y: Target Y in meters (positive = forward)
            linear_speed: Max speed in m/s (default 0.5, max ~1.555)
            flags: Drive behavior flags

        Returns:
            True if command sent successfully
        """
        return self._send(commands.drive_to_position_si(yaw_angle, x, y, linear_speed, flags))

    def drive_forward_meters(self, distance: float, speed: float = 0.5) -> bool:
        """Drive forward a specified distance in meters.

        Uses RVR's internal position controller for accurate movement.

        Args:
            distance: Distance in meters
            speed: Speed in m/s (default 0.5, max ~1.555)

        Returns:
            True if command sent
        """
        # Reset yaw so current orientation = heading 0
        self.reset_yaw()
        time.sleep(0.1)

        # Reset locator to origin (uses DID_SENSOR per SDK)
        self.reset_locator()
        time.sleep(0.1)

        # Drive to position (0, distance) = forward from current orientation
        self._send(commands.drive_to_position_si(0.0, 0.0, distance, speed, 0))

        # Wait for movement to complete (estimate based on distance/speed + buffer)
        estimated_time = (distance / speed) + 0.5
        time.sleep(estimated_time)

        return True

    def drive_backward_meters(self, distance: float, speed: float = 0.5) -> bool:
        """Drive backward a specified distance in meters.

        Uses RVR's internal position controller. Resets yaw first so
        backward is relative to current orientation.

        Args:
            distance: Distance in meters
            speed: Speed in m/s (default 0.5, max ~1.555)

        Returns:
            True if command sent
        """
        # Reset yaw so current orientation = heading 0
        self.reset_yaw()
        time.sleep(0.1)

        # Reset locator to origin
        self.reset_locator()
        time.sleep(0.1)

        # Drive to position (0, -distance) = backward from current orientation
        self._send(commands.drive_to_position_si(0.0, 0.0, -distance, speed, 0))

        # Wait for movement to complete
        estimated_time = (distance / speed) + 0.5
        time.sleep(estimated_time)

        return True
