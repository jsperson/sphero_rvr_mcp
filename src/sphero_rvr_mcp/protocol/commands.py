"""Pre-built RVR commands for direct serial."""

import struct
from .packet import build_packet, DID_DRIVE, DID_IO, DID_POWER, DID_SENSOR, TARGET_MCU, TARGET_BT

# Drive command IDs
CID_RAW_MOTORS = 0x01
CID_RESET_YAW = 0x06
CID_DRIVE_WITH_HEADING = 0x07
CID_RESET_LOCATOR = 0x13
CID_DRIVE_TO_POSITION_SI = 0x38

# IO command IDs
CID_SET_ALL_LEDS = 0x1A

# Power command IDs
CID_WAKE = 0x0D
CID_GET_BATTERY_PERCENTAGE = 0x10

# Sensor command IDs
CID_GET_RGBC_SENSOR = 0x23
CID_GET_AMBIENT_LIGHT = 0x30

# IR command IDs
DID_IR = 0x1C
CID_SEND_IR_MESSAGE = 0x38
CID_STOP_IR_BROADCAST = 0x39
CID_START_IR_BROADCAST = 0x3A


def wake() -> bytes:
    """Wake the RVR from sleep."""
    return build_packet(DID_POWER, CID_WAKE, TARGET_BT)


def drive_with_heading(speed: int, heading: int, flags: int = 0) -> bytes:
    """Drive at speed toward heading. flags: 0=forward, 1=reverse."""
    data = struct.pack(">BHB", speed & 0xFF, heading & 0xFFFF, flags & 0xFF)
    return build_packet(DID_DRIVE, CID_DRIVE_WITH_HEADING, TARGET_MCU, data)


def reset_yaw() -> bytes:
    """Reset yaw - set current heading as 0."""
    return build_packet(DID_DRIVE, CID_RESET_YAW, TARGET_MCU, b'')


def raw_motors(left_mode: int, left_speed: int, right_mode: int, right_speed: int) -> bytes:
    """Raw motor control. Modes: 0=off, 1=forward, 2=reverse."""
    data = struct.pack(">BBBB", left_mode, left_speed, right_mode, right_speed)
    return build_packet(DID_DRIVE, CID_RAW_MOTORS, TARGET_MCU, data)


def stop() -> bytes:
    """Stop the robot."""
    return drive_with_heading(0, 0, 0)


def set_all_leds(r: int, g: int, b: int) -> bytes:
    """Set all LEDs to RGB color."""
    # Bitmap: 30 bits for individual LED channels (not per-LED)
    # 0x3FFFFFFF = all LED channels enabled
    led_bitmap = 0x3FFFFFFF
    # 30 brightness values: RGB repeated for each of 10 LED groups
    brightness = bytes([r & 0xFF, g & 0xFF, b & 0xFF] * 10)
    data = struct.pack(">I", led_bitmap) + brightness
    return build_packet(DID_IO, CID_SET_ALL_LEDS, TARGET_BT, data)


def reset_locator() -> bytes:
    """Reset locator X,Y position to origin.

    Note: Uses DID_SENSOR (0x18) not DID_DRIVE (0x16) as per Sphero SDK.
    """
    return build_packet(DID_SENSOR, CID_RESET_LOCATOR, TARGET_MCU, b'')


def drive_to_position_si(yaw_angle: float, x: float, y: float, linear_speed: float, flags: int = 0) -> bytes:
    """Drive to position using SI units (meters).

    Args:
        yaw_angle: Target heading in degrees (CW negative, CCW positive)
        x: Target X coordinate in meters (positive = right)
        y: Target Y coordinate in meters (positive = forward)
        linear_speed: Max speed in m/s (max ~1.555 m/s)
        flags: Drive behavior flags (default 0)

    Returns:
        Command packet bytes

    Note: This command uses a simplified packet format (FLAGS=0x06) without
    target/source bytes, as per the Sphero CircuitPython SDK.
    """
    from .packet import SOP, EOP, escape_buffer, next_seq

    # Use simplified packet format (FLAGS=0x06 = no target/source, error-only response)
    FLAGS = 0x06
    DEVICE_ID = 0x16
    COMMAND_ID = 0x38
    seq = next_seq()

    # Build data payload
    data = struct.pack(">ffffB", yaw_angle, x, y, linear_speed, flags & 0xFF)

    # Build packet content (without SOP/EOP)
    content = bytes([FLAGS, DEVICE_ID, COMMAND_ID, seq]) + data

    # Calculate checksum
    chksum = (~(sum(content) % 256)) & 0xFF

    # Build final packet
    return bytes([SOP]) + escape_buffer(content + bytes([chksum])) + bytes([EOP])


def send_ir_message(code: int, strength: int = 32) -> bytes:
    """Send IR message. Code: 0-7, Strength: 0-64."""
    data = struct.pack(">BB", code & 0xFF, strength & 0xFF)
    return build_packet(DID_IR, CID_SEND_IR_MESSAGE, TARGET_BT, data)


def start_ir_broadcast(far_code: int, near_code: int) -> bytes:
    """Start IR broadcasting for robot-to-robot communication."""
    data = struct.pack(">BB", far_code & 0xFF, near_code & 0xFF)
    return build_packet(DID_IR, CID_START_IR_BROADCAST, TARGET_BT, data)


def stop_ir_broadcast() -> bytes:
    """Stop IR broadcasting."""
    return build_packet(DID_IR, CID_STOP_IR_BROADCAST, TARGET_BT, b'')


# Query commands (require response)

def get_battery_percentage() -> bytes:
    """Query battery percentage (0-100)."""
    return build_packet(DID_POWER, CID_GET_BATTERY_PERCENTAGE, TARGET_BT, b'', request_response=True)


def get_rgbc_sensor_values() -> bytes:
    """Query RGBC color sensor values."""
    return build_packet(DID_SENSOR, CID_GET_RGBC_SENSOR, TARGET_BT, b'', request_response=True)


def get_ambient_light() -> bytes:
    """Query ambient light sensor value."""
    return build_packet(DID_SENSOR, CID_GET_AMBIENT_LIGHT, TARGET_BT, b'', request_response=True)
