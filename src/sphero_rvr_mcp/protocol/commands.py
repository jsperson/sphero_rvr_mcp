"""Pre-built RVR commands for direct serial."""

import struct
from .packet import (
    build_packet, DID_SYSTEM_INFO, DID_DRIVE, DID_IO, DID_POWER, DID_SENSOR,
    TARGET_MCU, TARGET_BT
)

# Drive command IDs
CID_RAW_MOTORS = 0x01
CID_RESET_YAW = 0x06
CID_DRIVE_WITH_HEADING = 0x07
CID_RESET_LOCATOR = 0x13
CID_DRIVE_TO_POSITION_SI = 0x38

# IO command IDs
CID_SET_ALL_LEDS = 0x1A

# LED group mappings (bit positions in the 30-bit LED bitmap)
# Each LED group has 3 consecutive bits for R, G, B channels
# Bit positions: group_index * 3 + channel (0=R, 1=G, 2=B)
LED_GROUPS = {
    "headlight_right": 0,      # Bits 0-2
    "headlight_left": 1,       # Bits 3-5
    "battery_door_front": 2,   # Bits 6-8
    "battery_door_rear": 3,    # Bits 9-11
    "power_button_front": 4,   # Bits 12-14
    "power_button_rear": 5,    # Bits 15-17
    "brakelight_left": 6,      # Bits 18-20
    "brakelight_right": 7,     # Bits 21-23
    "status_indication_left": 8,   # Bits 24-26
    "status_indication_right": 9,  # Bits 27-29
}

# Power command IDs
CID_WAKE = 0x0D
CID_GET_BATTERY_PERCENTAGE = 0x10

# Sensor command IDs
CID_GET_RGBC_SENSOR = 0x23
CID_GET_AMBIENT_LIGHT = 0x30
CID_ENABLE_COLOR_DETECTION_NOTIFY = 0x35
CID_GET_CURRENT_DETECTED_COLOR = 0x37
CID_ENABLE_COLOR_DETECTION = 0x38

# IR command IDs
DID_IR = 0x1C
CID_SEND_IR_MESSAGE = 0x38
CID_STOP_IR_BROADCAST = 0x39
CID_START_IR_BROADCAST = 0x3A

# System Info command IDs (DID=0x11)
CID_GET_MAIN_APP_VERSION = 0x00
CID_GET_PROCESSOR_NAME = 0x1F
CID_GET_BOARD_REVISION = 0x03
CID_GET_MAC_ADDRESS = 0x06
CID_GET_SKU = 0x38
CID_GET_CORE_UPTIME = 0x39

# Extended Power command IDs (DID=0x13)
CID_GET_BATTERY_VOLTAGE_STATE = 0x17
CID_GET_BATTERY_VOLTAGE = 0x25
CID_GET_BATTERY_THRESHOLDS = 0x26

# Extended Sensor command IDs (DID=0x18)
CID_GET_IR_READINGS = 0x22
CID_CALIBRATE_MAGNETOMETER = 0x25
CID_START_IR_FOLLOWING = 0x28
CID_STOP_IR_FOLLOWING = 0x32
CID_START_IR_EVADING = 0x33
CID_STOP_IR_EVADING = 0x34
CID_GET_TEMPERATURE = 0x4A
CID_GET_THERMAL_PROTECTION = 0x4B
CID_GET_MAGNETOMETER = 0x52
CID_GET_ENCODER_COUNTS = 0x53

# Motor Protection command IDs (DID=0x16)
CID_ENABLE_MOTOR_STALL_NOTIFY = 0x25
CID_ENABLE_MOTOR_FAULT_NOTIFY = 0x27
CID_GET_MOTOR_FAULT = 0x29


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


def set_led_group(group_name: str, r: int, g: int, b: int) -> bytes:
    """Set a specific LED group to RGB color.

    Args:
        group_name: One of: headlight_left, headlight_right, battery_door_front,
                    battery_door_rear, power_button_front, power_button_rear,
                    brakelight_left, brakelight_right, status_indication_left,
                    status_indication_right
        r, g, b: Color values 0-255

    Returns:
        Command packet bytes

    Raises:
        ValueError: If group_name is not recognized
    """
    if group_name not in LED_GROUPS:
        raise ValueError(f"Unknown LED group: {group_name}. Valid groups: {list(LED_GROUPS.keys())}")

    group_index = LED_GROUPS[group_name]

    # Create bitmap with only this group's RGB channels enabled
    # Each group has 3 bits (R, G, B) starting at group_index * 3
    base_bit = group_index * 3
    led_bitmap = (1 << base_bit) | (1 << (base_bit + 1)) | (1 << (base_bit + 2))

    # Create brightness array with values only for this group
    # The brightness array must have 30 bytes (10 groups * 3 channels)
    # but only the enabled channels are used
    brightness = bytearray(30)
    brightness[base_bit] = r & 0xFF
    brightness[base_bit + 1] = g & 0xFF
    brightness[base_bit + 2] = b & 0xFF

    data = struct.pack(">I", led_bitmap) + bytes(brightness)
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


def enable_color_detection(enabled: bool = True) -> bytes:
    """Enable or disable color detection on bottom sensor (controls belly LED)."""
    data = struct.pack(">B", 1 if enabled else 0)
    return build_packet(DID_SENSOR, CID_ENABLE_COLOR_DETECTION, TARGET_BT, data, request_response=True)


def enable_color_detection_notify(enabled: bool = True, interval_ms: int = 250, confidence: int = 0) -> bytes:
    """Enable color detection with continuous notifications (turns on belly LED).

    Args:
        enabled: Turn on/off
        interval_ms: Notification interval in milliseconds
        confidence: Minimum confidence threshold (0-255)
    """
    data = struct.pack(">BHB", 1 if enabled else 0, interval_ms, confidence)
    return build_packet(DID_SENSOR, CID_ENABLE_COLOR_DETECTION_NOTIFY, TARGET_BT, data)


def get_current_detected_color() -> bytes:
    """Get current detected color reading (may trigger LED illumination)."""
    return build_packet(DID_SENSOR, CID_GET_CURRENT_DETECTED_COLOR, TARGET_BT, b'', request_response=True)


# ============================================================================
# Phase 1: Temperature Sensors
# ============================================================================

def get_temperature() -> bytes:
    """Query temperature sensors (motor and Nordic die temps).

    Returns sensor data with IDs: 4=left_motor, 5=right_motor, 8=nordic_die
    Response format: [id0, temp0(f32), id1, temp1(f32), ...]
    """
    # Sensor IDs: 4=left_motor, 5=right_motor
    data = struct.pack(">BB", 4, 5)  # Request left and right motor temps
    return build_packet(DID_SENSOR, CID_GET_TEMPERATURE, TARGET_MCU, data, request_response=True)


def get_thermal_protection_status() -> bytes:
    """Query motor thermal protection status.

    Response format: left_temp(f32), left_status(u8), right_temp(f32), right_status(u8)
    Status: 0=ok, 1=warning, 2=critical
    """
    return build_packet(DID_SENSOR, CID_GET_THERMAL_PROTECTION, TARGET_MCU, b'', request_response=True)


# ============================================================================
# Phase 2: System Information
# ============================================================================

def get_main_app_version(target: int = TARGET_BT) -> bytes:
    """Query firmware version (major.minor.revision).

    Args:
        target: TARGET_BT for Nordic, TARGET_MCU for ST MCU

    Response format: major(u16), minor(u16), revision(u16)
    """
    return build_packet(DID_SYSTEM_INFO, CID_GET_MAIN_APP_VERSION, target, b'', request_response=True)


def get_mac_address() -> bytes:
    """Query Bluetooth MAC address.

    Response format: null-terminated string
    """
    return build_packet(DID_SYSTEM_INFO, CID_GET_MAC_ADDRESS, TARGET_BT, b'', request_response=True)


def get_board_revision(target: int = TARGET_BT) -> bytes:
    """Query PCB board revision.

    Args:
        target: TARGET_BT for Nordic, TARGET_MCU for ST MCU

    Response format: revision(u8)
    """
    return build_packet(DID_SYSTEM_INFO, CID_GET_BOARD_REVISION, target, b'', request_response=True)


def get_processor_name(target: int = TARGET_BT) -> bytes:
    """Query processor identifier string.

    Args:
        target: TARGET_BT for Nordic, TARGET_MCU for ST MCU

    Response format: null-terminated string
    """
    return build_packet(DID_SYSTEM_INFO, CID_GET_PROCESSOR_NAME, target, b'', request_response=True)


def get_sku() -> bytes:
    """Query product SKU string.

    Response format: null-terminated string
    """
    return build_packet(DID_SYSTEM_INFO, CID_GET_SKU, TARGET_BT, b'', request_response=True)


def get_core_uptime(target: int = TARGET_BT) -> bytes:
    """Query core uptime in milliseconds since power-on.

    Args:
        target: TARGET_BT for Nordic, TARGET_MCU for ST MCU

    Response format: uptime(u64)
    """
    return build_packet(DID_SYSTEM_INFO, CID_GET_CORE_UPTIME, target, b'', request_response=True)


# ============================================================================
# Phase 3: Extended Battery Info
# ============================================================================

def get_battery_voltage() -> bytes:
    """Query battery voltage in volts.

    Response format: voltage(f32)
    """
    # 0 = calibrated_and_filtered reading type
    data = struct.pack(">B", 0)
    return build_packet(DID_POWER, CID_GET_BATTERY_VOLTAGE, TARGET_BT, data, request_response=True)


def get_battery_voltage_state() -> bytes:
    """Query battery voltage state.

    Response format: state(u8) - 0=unknown, 1=ok, 2=low, 3=critical
    """
    return build_packet(DID_POWER, CID_GET_BATTERY_VOLTAGE_STATE, TARGET_BT, b'', request_response=True)


def get_battery_thresholds() -> bytes:
    """Query battery voltage thresholds.

    Response format: critical(f32), low(f32), hysteresis(f32)
    """
    return build_packet(DID_POWER, CID_GET_BATTERY_THRESHOLDS, TARGET_BT, b'', request_response=True)


# ============================================================================
# Phase 4: Motion Sensors (Point Reads)
# ============================================================================

def get_encoder_counts() -> bytes:
    """Query wheel encoder tick counts.

    Response format: left(i32), right(i32)
    """
    return build_packet(DID_SENSOR, CID_GET_ENCODER_COUNTS, TARGET_MCU, b'', request_response=True)


def get_magnetometer() -> bytes:
    """Query magnetometer X, Y, Z readings.

    Response format: x(f32), y(f32), z(f32)
    """
    return build_packet(DID_SENSOR, CID_GET_MAGNETOMETER, TARGET_MCU, b'', request_response=True)


def calibrate_magnetometer() -> bytes:
    """Start magnetometer calibration (calibrate to north).

    This is an async operation - RVR will notify when complete.
    """
    return build_packet(DID_SENSOR, CID_CALIBRATE_MAGNETOMETER, TARGET_MCU, b'')


# ============================================================================
# Phase 5: Motor Protection
# ============================================================================

def get_motor_fault_state() -> bytes:
    """Query if motor fault is currently active.

    Response format: is_fault(u8) - 0=no fault, 1=fault active
    """
    return build_packet(DID_DRIVE, CID_GET_MOTOR_FAULT, TARGET_MCU, b'', request_response=True)


def enable_motor_stall_notify(enabled: bool = True) -> bytes:
    """Enable/disable motor stall detection notifications.

    Args:
        enabled: True to enable, False to disable
    """
    data = struct.pack(">B", 1 if enabled else 0)
    return build_packet(DID_DRIVE, CID_ENABLE_MOTOR_STALL_NOTIFY, TARGET_MCU, data)


def enable_motor_fault_notify(enabled: bool = True) -> bytes:
    """Enable/disable motor fault detection notifications.

    Args:
        enabled: True to enable, False to disable
    """
    data = struct.pack(">B", 1 if enabled else 0)
    return build_packet(DID_DRIVE, CID_ENABLE_MOTOR_FAULT_NOTIFY, TARGET_MCU, data)


# ============================================================================
# Phase 6: IR Follow/Evade
# ============================================================================

def start_ir_following(far_code: int, near_code: int) -> bytes:
    """Start following an IR-broadcasting robot.

    Args:
        far_code: IR code to follow when far (0-7)
        near_code: IR code to follow when near (0-7)
    """
    data = struct.pack(">BB", far_code & 0xFF, near_code & 0xFF)
    return build_packet(DID_SENSOR, CID_START_IR_FOLLOWING, TARGET_BT, data)


def stop_ir_following() -> bytes:
    """Stop IR following behavior."""
    return build_packet(DID_SENSOR, CID_STOP_IR_FOLLOWING, TARGET_BT, b'')


def start_ir_evading(far_code: int, near_code: int) -> bytes:
    """Start evading an IR-broadcasting robot.

    Args:
        far_code: IR code to evade when far (0-7)
        near_code: IR code to evade when near (0-7)
    """
    data = struct.pack(">BB", far_code & 0xFF, near_code & 0xFF)
    return build_packet(DID_SENSOR, CID_START_IR_EVADING, TARGET_BT, data)


def stop_ir_evading() -> bytes:
    """Stop IR evading behavior."""
    return build_packet(DID_SENSOR, CID_STOP_IR_EVADING, TARGET_BT, b'')


def get_ir_readings() -> bytes:
    """Query all 4 IR sensor readings.

    Response format: single uint32_t with 8-bit values packed:
        bits 0-7: front_left, bits 8-15: front_right,
        bits 16-23: back_right, bits 24-31: back_left
    """
    return build_packet(DID_SENSOR, CID_GET_IR_READINGS, TARGET_MCU, b'', request_response=True)
