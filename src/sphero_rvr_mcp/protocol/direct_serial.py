"""Direct serial connection to RVR - bypasses SDK async overhead."""

import logging
import serial
import threading
import time
from typing import Optional
from . import commands
from .packet import parse_response, ParsedResponse, get_packet_header
from .dispatcher import SerialDispatcher
from .movement import MovementTracker

logger = logging.getLogger(__name__)


class DirectSerial:
    """Synchronous direct serial connection to RVR for low-latency commands.

    This class provides two modes of operation:
    1. Legacy mode: Simple send/receive with inline blocking reads
    2. Dispatcher mode: Background reader with sequence matching (SDK-style)

    Dispatcher mode is automatically enabled on connect() and provides:
    - Proper request-response matching by sequence number
    - Movement completion detection via notifications
    - Better handling of concurrent commands
    """

    def __init__(self, port: str = "/dev/ttyS0", baud: int = 115200):
        self._port = port
        self._baud = baud
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()

        # Dispatcher for SDK-style communication
        self._dispatcher: Optional[SerialDispatcher] = None
        self._movement_tracker: Optional[MovementTracker] = None

        # Feature flags
        self._use_dispatcher = False  # Disabled - causing stability issues
        self._use_movement_notifications = False  # Disabled with dispatcher

    def connect(self) -> bool:
        """Open serial connection and start dispatcher."""
        with self._lock:
            if self._serial and self._serial.is_open:
                return True
            try:
                self._serial = serial.Serial(self._port, self._baud, timeout=0.1)

                # Start dispatcher if enabled
                if self._use_dispatcher:
                    self._start_dispatcher()

                return True
            except Exception as e:
                logger.error(f"Failed to connect: {e}")
                return False

    def disconnect(self):
        """Close serial connection and stop dispatcher."""
        with self._lock:
            # Stop dispatcher first
            if self._dispatcher:
                self._stop_dispatcher()

            if self._serial:
                self._serial.close()
                self._serial = None

    def _start_dispatcher(self) -> None:
        """Start the serial dispatcher and movement tracker.

        Must be called with lock held.
        """
        if not self._serial:
            return

        try:
            self._dispatcher = SerialDispatcher(self._serial)
            self._dispatcher.start()

            # Create and register movement tracker
            if self._use_movement_notifications:
                self._movement_tracker = MovementTracker()
                self._movement_tracker.register_with_dispatcher(self._dispatcher)

            logger.debug("Dispatcher started successfully")
        except Exception as e:
            logger.error(f"Failed to start dispatcher: {e}")
            self._dispatcher = None
            self._movement_tracker = None

    def _stop_dispatcher(self) -> None:
        """Stop the serial dispatcher and movement tracker.

        Must be called with lock held.
        """
        if self._movement_tracker and self._dispatcher:
            try:
                self._movement_tracker.unregister_from_dispatcher(self._dispatcher)
            except Exception as e:
                logger.warning(f"Error unregistering movement tracker: {e}")
            self._movement_tracker = None

        if self._dispatcher:
            try:
                self._dispatcher.stop()
            except Exception as e:
                logger.warning(f"Error stopping dispatcher: {e}")
            self._dispatcher = None

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def dispatcher(self) -> Optional[SerialDispatcher]:
        """Get the serial dispatcher (if active)."""
        return self._dispatcher

    @property
    def movement_tracker(self) -> Optional[MovementTracker]:
        """Get the movement tracker (if active)."""
        return self._movement_tracker

    def _send(self, packet: bytes) -> bool:
        """Send packet (fire-and-forget)."""
        with self._lock:
            if not self._serial or not self._serial.is_open:
                return False
            try:
                self._serial.write(packet)
                self._serial.flush()
                return True
            except Exception as e:
                logger.error(f"Send failed: {e}")
                return False

    def _drain_buffer(self) -> int:
        """Drain any pending data from serial buffer.

        Returns:
            Number of bytes drained
        """
        if not self._serial or not self._serial.is_open:
            return 0
        total = 0
        try:
            while self._serial.in_waiting > 0:
                data = self._serial.read(self._serial.in_waiting)
                total += len(data)
                logger.debug(f"Drained {len(data)} bytes from buffer")
        except Exception as e:
            logger.warning(f"Error draining buffer: {e}")
        return total

    def _send_and_wait(self, packet: bytes, timeout: float = 1.0) -> Optional[ParsedResponse]:
        """Send packet and wait for response.

        Uses the dispatcher if available for proper sequence matching,
        otherwise falls back to inline blocking read.

        Args:
            packet: Command packet to send
            timeout: Maximum time to wait for response (seconds)

        Returns:
            ParsedResponse if received, None on timeout or error
        """
        # Try dispatcher path first (SDK-style)
        if self._dispatcher:
            try:
                did, cid, seq = get_packet_header(packet)
                response = self._dispatcher.send_and_wait(packet, did, cid, seq, timeout)
                if response is not None:
                    return response
                # Dispatcher returned None - might not be running, fall through
            except Exception as e:
                logger.debug(f"Dispatcher send_and_wait failed: {e}, using fallback")

        # Fallback to legacy inline blocking read
        return self._send_and_wait_legacy(packet, timeout)

    def _send_and_wait_legacy(self, packet: bytes, timeout: float = 1.0) -> Optional[ParsedResponse]:
        """Legacy send and wait using inline blocking read.

        This is the fallback when dispatcher is not available.

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
            except Exception as e:
                logger.error(f"Legacy send_and_wait failed: {e}")
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
        self._drain_buffer()  # Clear async data before drive
        flags = 1 if reverse else 0
        return self._send(commands.drive_with_heading(speed, heading, flags))

    def raw_motors(self, left_speed: int, right_speed: int) -> bool:
        """Direct motor control. Negative = reverse."""
        self._drain_buffer()  # Clear async data before drive
        left_mode = 2 if left_speed < 0 else (1 if left_speed > 0 else 0)
        right_mode = 2 if right_speed < 0 else (1 if right_speed > 0 else 0)
        return self._send(commands.raw_motors(
            left_mode, abs(left_speed),
            right_mode, abs(right_speed)
        ))

    def stop(self) -> bool:
        """Stop the robot."""
        self._drain_buffer()  # Clear async data
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
        If movement tracker is available, waits for completion notification.
        Otherwise falls back to time-based estimation.

        Args:
            distance: Distance in meters
            speed: Speed in m/s (default 0.5, max ~1.555)

        Returns:
            True if movement completed successfully
        """
        self._drain_buffer()  # Clear async data before drive

        # Reset yaw so current orientation = heading 0
        self.reset_yaw()
        time.sleep(0.1)

        # Reset locator to origin (uses DID_SENSOR per SDK)
        self.reset_locator()
        time.sleep(0.1)

        # Calculate fallback time in case notification doesn't arrive
        estimated_time = (distance / speed) + 0.5

        # Start movement tracking if available
        if self._movement_tracker and self._use_movement_notifications:
            self._movement_tracker.start_movement(timeout=estimated_time + 2.0)

        # Send drive command
        self._send(commands.drive_to_position_si(0.0, 0.0, distance, speed, 0))

        # Wait for completion
        if self._movement_tracker and self._use_movement_notifications:
            # Wait for notification with fallback
            completed = self._movement_tracker.wait_for_completion(
                timeout=estimated_time + 2.0,
                fallback_time=estimated_time
            )
            logger.debug(f"drive_forward_meters: completed={completed}")
            return completed
        else:
            # Fallback: time-based estimation
            time.sleep(estimated_time)
            return True

    def drive_backward_meters(self, distance: float, speed: float = 0.5) -> bool:
        """Drive backward a specified distance in meters.

        Uses RVR's internal position controller with reverse flag (0x01)
        for accurate backward movement without turning around.

        Args:
            distance: Distance in meters
            speed: Speed in m/s (default 0.5, max ~1.555)

        Returns:
            True if movement completed successfully
        """
        self._drain_buffer()  # Clear async data before drive

        # Reset yaw so current orientation = heading 0
        self.reset_yaw()
        time.sleep(0.1)

        # Reset locator to origin
        self.reset_locator()
        time.sleep(0.1)

        # Calculate fallback time
        estimated_time = (distance / speed) + 0.5

        # Start movement tracking if available
        if self._movement_tracker and self._use_movement_notifications:
            self._movement_tracker.start_movement(timeout=estimated_time + 2.0)

        # Send drive command with reverse flag (0x01)
        # Drive to negative Y (behind us) with reverse flag = drive backward without turning
        self._send(commands.drive_to_position_si(0.0, 0.0, -distance, speed, 0x01))

        # Wait for completion
        if self._movement_tracker and self._use_movement_notifications:
            completed = self._movement_tracker.wait_for_completion(
                timeout=estimated_time + 2.0,
                fallback_time=estimated_time
            )
            logger.debug(f"drive_backward_meters: completed={completed}")
            return completed
        else:
            # Fallback: time-based estimation
            time.sleep(estimated_time)
            return True

    # ========================================================================
    # Phase 1: Temperature Sensors
    # ========================================================================

    def get_temperature(self, timeout: float = 1.0) -> Optional[dict]:
        """Get temperature sensor readings.

        Returns:
            Dict with sensor temps in Celsius:
            {'left_motor': float, 'right_motor': float, 'nordic_die': float}
            or None on error
        """
        import struct
        packet = commands.get_temperature()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 5:
            # Response format: [id0, temp0(f32), id1, temp1(f32), ...]
            result = {}
            sensor_names = {4: 'left_motor', 5: 'right_motor', 8: 'nordic_die'}
            i = 0
            while i + 4 < len(response.data):
                sensor_id = response.data[i]
                temp = struct.unpack('>f', response.data[i+1:i+5])[0]
                if sensor_id in sensor_names:
                    result[sensor_names[sensor_id]] = temp
                i += 5
            return result if result else None
        return None

    def get_thermal_protection_status(self, timeout: float = 1.0) -> Optional[dict]:
        """Get motor thermal protection status.

        Returns:
            Dict with thermal protection info:
            {'left_temp': float, 'left_status': int,
             'right_temp': float, 'right_status': int}
            Status: 0=ok, 1=warning, 2=critical
            or None on error
        """
        import struct
        packet = commands.get_thermal_protection_status()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 10:
            # Response: left_temp(f32), left_status(u8), right_temp(f32), right_status(u8)
            left_temp = struct.unpack('>f', response.data[0:4])[0]
            left_status = response.data[4]
            right_temp = struct.unpack('>f', response.data[5:9])[0]
            right_status = response.data[9]
            return {
                'left_temp': left_temp,
                'left_status': left_status,
                'right_temp': right_temp,
                'right_status': right_status,
            }
        return None

    # ========================================================================
    # Phase 2: System Information
    # ========================================================================

    def get_firmware_version(self, target: int = 0x01, timeout: float = 1.0) -> Optional[dict]:
        """Get firmware version.

        Args:
            target: 0x01 for Nordic (BT), 0x02 for ST MCU

        Returns:
            Dict with 'major', 'minor', 'revision' or None on error
        """
        import struct
        from .packet import TARGET_BT, TARGET_MCU
        target_val = TARGET_BT if target == 0x01 else TARGET_MCU
        packet = commands.get_main_app_version(target_val)
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 6:
            major, minor, revision = struct.unpack('>HHH', response.data[:6])
            return {'major': major, 'minor': minor, 'revision': revision}
        return None

    def get_mac_address(self, timeout: float = 1.0) -> Optional[str]:
        """Get Bluetooth MAC address.

        Returns:
            MAC address string or None on error
        """
        packet = commands.get_mac_address()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) > 0:
            # Null-terminated string
            mac = response.data.split(b'\x00')[0].decode('ascii', errors='ignore')
            return mac if mac else None
        return None

    def get_board_revision(self, target: int = 0x01, timeout: float = 1.0) -> Optional[int]:
        """Get PCB board revision.

        Args:
            target: 0x01 for Nordic (BT), 0x02 for ST MCU

        Returns:
            Board revision number or None on error
        """
        from .packet import TARGET_BT, TARGET_MCU
        target_val = TARGET_BT if target == 0x01 else TARGET_MCU
        packet = commands.get_board_revision(target_val)
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 1:
            return response.data[0]
        return None

    def get_processor_name(self, target: int = 0x01, timeout: float = 1.0) -> Optional[str]:
        """Get processor identifier string.

        Args:
            target: 0x01 for Nordic (BT), 0x02 for ST MCU

        Returns:
            Processor name string or None on error
        """
        from .packet import TARGET_BT, TARGET_MCU
        target_val = TARGET_BT if target == 0x01 else TARGET_MCU
        packet = commands.get_processor_name(target_val)
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) > 0:
            # Null-terminated string
            name = response.data.split(b'\x00')[0].decode('ascii', errors='ignore')
            return name if name else None
        return None

    def get_sku(self, timeout: float = 1.0) -> Optional[str]:
        """Get product SKU string.

        Returns:
            SKU string or None on error
        """
        packet = commands.get_sku()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) > 0:
            # Null-terminated string
            sku = response.data.split(b'\x00')[0].decode('ascii', errors='ignore')
            return sku if sku else None
        return None

    def get_core_uptime(self, target: int = 0x01, timeout: float = 1.0) -> Optional[int]:
        """Get core uptime in milliseconds since power-on.

        Args:
            target: 0x01 for Nordic (BT), 0x02 for ST MCU

        Returns:
            Uptime in milliseconds or None on error
        """
        import struct
        from .packet import TARGET_BT, TARGET_MCU
        target_val = TARGET_BT if target == 0x01 else TARGET_MCU
        packet = commands.get_core_uptime(target_val)
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 8:
            uptime = struct.unpack('>Q', response.data[:8])[0]
            return uptime
        return None

    # ========================================================================
    # Phase 3: Extended Battery Info
    # ========================================================================

    def get_battery_voltage(self, timeout: float = 1.0) -> Optional[float]:
        """Get battery voltage in volts.

        Returns:
            Voltage as float or None on error
        """
        import struct
        packet = commands.get_battery_voltage()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 4:
            voltage = struct.unpack('>f', response.data[:4])[0]
            return voltage
        return None

    def get_battery_voltage_state(self, timeout: float = 1.0) -> Optional[dict]:
        """Get battery voltage state.

        Returns:
            Dict with 'state' (0=unknown, 1=ok, 2=low, 3=critical)
            and 'state_name' string, or None on error
        """
        packet = commands.get_battery_voltage_state()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 1:
            state = response.data[0]
            state_names = {0: 'unknown', 1: 'ok', 2: 'low', 3: 'critical'}
            return {
                'state': state,
                'state_name': state_names.get(state, 'unknown'),
            }
        return None

    def get_battery_thresholds(self, timeout: float = 1.0) -> Optional[dict]:
        """Get battery voltage thresholds.

        Returns:
            Dict with 'critical', 'low', 'hysteresis' voltages
            or None on error
        """
        import struct
        packet = commands.get_battery_thresholds()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 12:
            critical, low, hysteresis = struct.unpack('>fff', response.data[:12])
            return {
                'critical': critical,
                'low': low,
                'hysteresis': hysteresis,
            }
        return None

    # ========================================================================
    # Phase 4: Motion Sensors (Point Reads)
    # ========================================================================

    def get_encoder_counts(self, timeout: float = 1.0) -> Optional[dict]:
        """Get wheel encoder tick counts.

        Returns:
            Dict with 'left' and 'right' tick counts or None on error
        """
        import struct
        packet = commands.get_encoder_counts()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 8:
            left, right = struct.unpack('>ii', response.data[:8])
            return {'left': left, 'right': right}
        return None

    def get_magnetometer(self, timeout: float = 1.0) -> Optional[dict]:
        """Get magnetometer X, Y, Z readings.

        Returns:
            Dict with 'x', 'y', 'z' magnetic field values or None on error
        """
        import struct
        packet = commands.get_magnetometer()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 12:
            x, y, z = struct.unpack('>fff', response.data[:12])
            return {'x': x, 'y': y, 'z': z}
        return None

    def calibrate_magnetometer(self) -> bool:
        """Start magnetometer calibration (calibrate to north).

        This is an async operation - RVR will notify when complete.

        Returns:
            True if command sent successfully
        """
        return self._send(commands.calibrate_magnetometer())

    # ========================================================================
    # Phase 5: Motor Protection
    # ========================================================================

    def get_motor_fault_state(self, timeout: float = 1.0) -> Optional[bool]:
        """Check if motor fault is currently active.

        Returns:
            True if fault active, False if no fault, None on error
        """
        packet = commands.get_motor_fault_state()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 1:
            return response.data[0] != 0
        return None

    def enable_motor_stall_notify(self, enabled: bool = True) -> bool:
        """Enable/disable motor stall detection notifications.

        Args:
            enabled: True to enable, False to disable

        Returns:
            True if command sent successfully
        """
        return self._send(commands.enable_motor_stall_notify(enabled))

    def enable_motor_fault_notify(self, enabled: bool = True) -> bool:
        """Enable/disable motor fault detection notifications.

        Args:
            enabled: True to enable, False to disable

        Returns:
            True if command sent successfully
        """
        return self._send(commands.enable_motor_fault_notify(enabled))

    # ========================================================================
    # Phase 6: IR Follow/Evade
    # ========================================================================

    def start_ir_following(self, far_code: int, near_code: int) -> bool:
        """Start following an IR-broadcasting robot.

        Args:
            far_code: IR code to follow when far (0-7)
            near_code: IR code to follow when near (0-7)

        Returns:
            True if command sent successfully
        """
        return self._send(commands.start_ir_following(far_code, near_code))

    def stop_ir_following(self) -> bool:
        """Stop IR following behavior.

        Returns:
            True if command sent successfully
        """
        return self._send(commands.stop_ir_following())

    def start_ir_evading(self, far_code: int, near_code: int) -> bool:
        """Start evading an IR-broadcasting robot.

        Args:
            far_code: IR code to evade when far (0-7)
            near_code: IR code to evade when near (0-7)

        Returns:
            True if command sent successfully
        """
        return self._send(commands.start_ir_evading(far_code, near_code))

    def stop_ir_evading(self) -> bool:
        """Stop IR evading behavior.

        Returns:
            True if command sent successfully
        """
        return self._send(commands.stop_ir_evading())

    def get_ir_readings(self, timeout: float = 1.0) -> Optional[dict]:
        """Get all 4 IR sensor readings.

        Returns:
            Dict with 'front_left', 'front_right', 'back_right', 'back_left'
            values (0-255) or None on error. Value of 255 means no IR message
            received on that sensor.
        """
        import struct
        packet = commands.get_ir_readings()
        response = self._send_and_wait(packet, timeout)
        if response and len(response.data) >= 4:
            # Response is a single uint32_t with 8-bit values packed:
            # bits 0-7: front_left, bits 8-15: front_right,
            # bits 16-23: back_right, bits 24-31: back_left
            sensor_data = struct.unpack('>I', response.data[:4])[0]
            return {
                'front_left': sensor_data & 0xFF,
                'front_right': (sensor_data >> 8) & 0xFF,
                'back_right': (sensor_data >> 16) & 0xFF,
                'back_left': (sensor_data >> 24) & 0xFF,
            }
        return None
