"""Sphero RVR MCP Server - Main server with tool definitions."""

from typing import Optional
from fastmcp import FastMCP

from .config import RvrConfig, load_config_from_env
from .rvr_manager import RvrManager
from .sensor_manager import SensorManager
from .safety_controller import SafetyController

# Create FastMCP server instance
mcp = FastMCP("sphero-rvr")

# Global state (initialized on connect)
_config: Optional[RvrConfig] = None
_rvr_manager: Optional[RvrManager] = None
_sensor_manager: Optional[SensorManager] = None
_safety_controller: Optional[SafetyController] = None


def _ensure_initialized() -> tuple[RvrManager, SensorManager, SafetyController]:
    """Ensure managers are initialized and return them.

    Raises:
        RuntimeError: If not connected.
    """
    if _rvr_manager is None or _sensor_manager is None or _safety_controller is None:
        raise RuntimeError("Not connected to RVR. Call connect() first.")
    return _rvr_manager, _sensor_manager, _safety_controller


# =============================================================================
# Connection Tools
# =============================================================================

@mcp.tool()
async def connect(port: str = "/dev/ttyS0", baud: int = 115200) -> dict:
    """Connect to the Sphero RVR robot and wake it up.

    Args:
        port: Serial port (default: /dev/ttyS0).
        baud: Baud rate (default: 115200).

    Returns:
        Connection result with success status and message.
    """
    global _config, _rvr_manager, _sensor_manager, _safety_controller

    _config = load_config_from_env()
    _config.serial.port = port
    _config.serial.baud_rate = baud

    _rvr_manager = RvrManager(_config)
    _sensor_manager = SensorManager(_rvr_manager, _config.sensors)
    _safety_controller = SafetyController(
        _config.safety, _rvr_manager, _sensor_manager
    )

    try:
        success = await _rvr_manager.connect()
        return {
            "success": success,
            "message": "RVR connected and awake" if success else "Connection failed"
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@mcp.tool()
async def disconnect() -> dict:
    """Safely disconnect from the RVR.

    Returns:
        Disconnection result.
    """
    global _rvr_manager, _sensor_manager, _safety_controller

    if _rvr_manager is None:
        return {"success": True, "message": "Already disconnected"}

    try:
        # Stop streaming first
        if _sensor_manager:
            await _sensor_manager.stop_streaming()

        success = await _rvr_manager.disconnect()
        return {
            "success": success,
            "message": "Disconnected from RVR" if success else "Disconnect failed"
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@mcp.tool()
async def get_connection_status() -> dict:
    """Get current connection status.

    Returns:
        Connection status including uptime and firmware version.
    """
    if _rvr_manager is None:
        return {
            "connected": False,
            "uptime_seconds": None,
            "firmware_version": None,
            "mac_address": None
        }

    return {
        "connected": _rvr_manager.is_connected,
        "uptime_seconds": _rvr_manager.uptime_seconds,
        "firmware_version": _rvr_manager.firmware_version,
        "mac_address": _rvr_manager.mac_address
    }


# =============================================================================
# Movement Tools
# =============================================================================

@mcp.tool()
async def drive_with_heading(
    speed: int,
    heading: int,
    reverse: bool = False
) -> dict:
    """Drive the RVR at a given speed toward a heading.

    Args:
        speed: Speed 0-255 (will be limited by safety settings).
        heading: Heading 0-359 degrees (0 = forward).
        reverse: If True, drive in reverse.

    Returns:
        Drive result with actual speed applied.
    """
    try:
        rvr_mgr, _, safety = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await safety.on_movement_command()
        actual_speed, was_limited = safety.limit_speed(speed)

        from sphero_sdk import DriveFlagsBitmask
        flags = DriveFlagsBitmask.drive_reverse.value if reverse else DriveFlagsBitmask.none.value

        await rvr_mgr.rvr.drive_with_heading(
            speed=actual_speed,
            heading=heading % 360,
            flags=flags
        )

        return {
            "success": True,
            "actual_speed": actual_speed,
            "heading": heading % 360,
            "limited": was_limited
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def drive_tank(left_velocity: float, right_velocity: float) -> dict:
    """Drive using tank controls (independent left/right velocities).

    Args:
        left_velocity: Left track velocity in m/s (-1.5 to 1.5).
        right_velocity: Right track velocity in m/s (-1.5 to 1.5).

    Returns:
        Drive result with actual velocities applied.
    """
    try:
        rvr_mgr, _, safety = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await safety.on_movement_command()
        actual_left, left_limited = safety.limit_velocity(left_velocity)
        actual_right, right_limited = safety.limit_velocity(right_velocity)

        await rvr_mgr.rvr.drive_tank_si_units(
            left_velocity=actual_left,
            right_velocity=actual_right
        )

        return {
            "success": True,
            "actual_left_velocity": actual_left,
            "actual_right_velocity": actual_right,
            "limited": left_limited or right_limited
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def drive_rc(linear_velocity: float, yaw_velocity: float) -> dict:
    """Drive using RC-style controls (linear + yaw).

    Args:
        linear_velocity: Forward/backward velocity in m/s (-1.5 to 1.5).
        yaw_velocity: Turning rate in degrees/second.

    Returns:
        Drive result with actual velocities applied.
    """
    try:
        rvr_mgr, _, safety = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await safety.on_movement_command()
        actual_linear, limited = safety.limit_velocity(linear_velocity)

        await rvr_mgr.rvr.drive_rc_si_units(
            linear_velocity=actual_linear,
            yaw_angular_velocity=yaw_velocity,
            flags=0
        )

        return {
            "success": True,
            "actual_linear_velocity": actual_linear,
            "yaw_velocity": yaw_velocity,
            "limited": limited
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def drive_to_position(
    x: float,
    y: float,
    speed: float,
    final_heading: float = 0
) -> dict:
    """Drive to an X,Y position relative to current location.

    Args:
        x: X position in meters.
        y: Y position in meters.
        speed: Travel speed in m/s.
        final_heading: Final heading in degrees after reaching position.

    Returns:
        Drive result.
    """
    try:
        rvr_mgr, _, safety = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await safety.on_movement_command()
        actual_speed, limited = safety.limit_velocity(speed)

        await rvr_mgr.rvr.drive_to_position_si(
            yaw_angle=final_heading,
            x=x,
            y=y,
            linear_speed=actual_speed,
            flags=0
        )

        return {
            "success": True,
            "target_x": x,
            "target_y": y,
            "actual_speed": actual_speed,
            "limited": limited
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def stop(deceleration: Optional[float] = None) -> dict:
    """Stop the RVR.

    Args:
        deceleration: Optional custom deceleration rate.

    Returns:
        Stop result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        if deceleration is not None:
            await rvr_mgr.rvr.drive_stop_custom_decel(deceleration_rate=deceleration)
        else:
            await rvr_mgr.rvr.drive_stop()

        return {"success": True, "message": "RVR stopped"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def emergency_stop() -> dict:
    """Execute emergency stop - immediately stops motors and blocks further movement.

    Call clear_emergency_stop() to allow movement again.

    Returns:
        Emergency stop result.
    """
    try:
        _, _, safety = _ensure_initialized()
        success = await safety.emergency_stop()
        return {
            "success": success,
            "message": "Emergency stop activated. Call clear_emergency_stop() to resume."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def clear_emergency_stop() -> dict:
    """Clear emergency stop to allow movement again.

    Returns:
        Result of clearing emergency stop.
    """
    try:
        _, _, safety = _ensure_initialized()
        safety.clear_emergency_stop()
        return {"success": True, "message": "Emergency stop cleared. Movement allowed."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def reset_yaw() -> dict:
    """Reset yaw - set current heading as 0 degrees.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await rvr_mgr.rvr.reset_yaw()
        return {"success": True, "message": "Yaw reset to 0"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def reset_locator() -> dict:
    """Reset locator - set current position as origin (0, 0).

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await rvr_mgr.rvr.reset_locator_x_and_y()
        return {"success": True, "message": "Locator reset to (0, 0)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# LED Tools
# =============================================================================

@mcp.tool()
async def set_all_leds(red: int, green: int, blue: int) -> dict:
    """Set all LEDs to the same color.

    Args:
        red: Red component 0-255.
        green: Green component 0-255.
        blue: Blue component 0-255.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await rvr_mgr.rvr.led_control.set_all_leds_rgb(
            red=max(0, min(255, red)),
            green=max(0, min(255, green)),
            blue=max(0, min(255, blue))
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def set_led(led_group: str, red: int, green: int, blue: int) -> dict:
    """Set a specific LED group to a color.

    Args:
        led_group: LED group name (headlight_left, headlight_right, brakelight_left,
                   brakelight_right, status_indication_left, status_indication_right,
                   battery_door_front, battery_door_rear, power_button_front,
                   power_button_rear, undercarriage_white).
        red: Red component 0-255.
        green: Green component 0-255.
        blue: Blue component 0-255.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        from sphero_sdk import RvrLedGroups

        led_groups_map = {
            "headlight_left": RvrLedGroups.headlight_left,
            "headlight_right": RvrLedGroups.headlight_right,
            "brakelight_left": RvrLedGroups.brakelight_left,
            "brakelight_right": RvrLedGroups.brakelight_right,
            "status_indication_left": RvrLedGroups.status_indication_left,
            "status_indication_right": RvrLedGroups.status_indication_right,
            "battery_door_front": RvrLedGroups.battery_door_front,
            "battery_door_rear": RvrLedGroups.battery_door_rear,
            "power_button_front": RvrLedGroups.power_button_front,
            "power_button_rear": RvrLedGroups.power_button_rear,
            "undercarriage_white": RvrLedGroups.undercarriage_white,
        }

        led_enum = led_groups_map.get(led_group.lower())
        if led_enum is None:
            return {
                "success": False,
                "error": f"Unknown LED group: {led_group}. Valid groups: {list(led_groups_map.keys())}"
            }

        await rvr_mgr.rvr.led_control.set_led_rgb(
            led=led_enum,
            red=max(0, min(255, red)),
            green=max(0, min(255, green)),
            blue=max(0, min(255, blue))
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def turn_leds_off() -> dict:
    """Turn off all LEDs.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await rvr_mgr.rvr.led_control.set_all_leds_rgb(red=0, green=0, blue=0)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Sensor Tools
# =============================================================================

@mcp.tool()
async def start_sensor_streaming(
    sensors: list[str],
    interval_ms: int = 250
) -> dict:
    """Start streaming sensor data in the background.

    Args:
        sensors: List of sensors to stream. Options: accelerometer, gyroscope,
                 imu, locator, velocity, speed, quaternion, color_detection,
                 ambient_light, encoders, core_time.
        interval_ms: Streaming interval in milliseconds (min 50).

    Returns:
        Result with list of enabled sensors.
    """
    try:
        _, sensor_mgr, _ = _ensure_initialized()

        enabled = await sensor_mgr.start_streaming(sensors, interval_ms)
        return {
            "success": len(enabled) > 0,
            "sensors_enabled": enabled,
            "interval_ms": interval_ms
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def stop_sensor_streaming() -> dict:
    """Stop all sensor streaming.

    Returns:
        Result.
    """
    try:
        _, sensor_mgr, _ = _ensure_initialized()

        success = await sensor_mgr.stop_streaming()
        return {"success": success}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_sensor_data(sensors: Optional[list[str]] = None) -> dict:
    """Get current sensor data from streaming cache.

    Args:
        sensors: Specific sensors to get, or None for all streaming sensors.

    Returns:
        Sensor data with timestamps.
    """
    try:
        _, sensor_mgr, _ = _ensure_initialized()

        data = await sensor_mgr.get_streaming_data(sensors)
        return {"success": True, "sensors": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_ambient_light() -> dict:
    """Query ambient light sensor directly (not from streaming cache).

    Returns:
        Ambient light value.
    """
    try:
        _, sensor_mgr, _ = _ensure_initialized()

        value = await sensor_mgr.query_ambient_light()
        if value is not None:
            return {"success": True, "value": value, "unit": "lux"}
        return {"success": False, "error": "Failed to read ambient light"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def enable_color_detection(enabled: bool = True) -> dict:
    """Enable or disable the color sensor's illumination LED.

    Must be enabled before color detection will return valid readings.

    Args:
        enabled: True to enable, False to disable.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await rvr_mgr.rvr.enable_color_detection(is_enabled=enabled)
        return {
            "success": True,
            "enabled": enabled,
            "message": "Color detection LED enabled" if enabled else "Color detection LED disabled"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_color_detection() -> dict:
    """Query color sensor directly (not from streaming cache).

    Automatically enables the illumination LED, reads the color, then disables the LED.

    Returns:
        Color values (R, G, B, C).
    """
    try:
        rvr_mgr, sensor_mgr, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        # Enable illumination LED
        await rvr_mgr.rvr.enable_color_detection(is_enabled=True)

        # Brief pause to let sensor stabilize
        import asyncio
        await asyncio.sleep(0.1)

        # Read color
        color = await sensor_mgr.query_color_detection()

        # Disable illumination LED
        await rvr_mgr.rvr.enable_color_detection(is_enabled=False)

        if color is not None:
            return {"success": True, **color}
        return {"success": False, "error": "Failed to read color sensor"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Battery and System Tools
# =============================================================================

@mcp.tool()
async def get_battery_status() -> dict:
    """Get battery status.

    Returns:
        Battery percentage, voltage, and state.
    """
    try:
        _, sensor_mgr, _ = _ensure_initialized()

        percentage = await sensor_mgr.query_battery_percentage()
        voltage_info = await sensor_mgr.query_battery_voltage()

        return {
            "success": True,
            "percentage": percentage,
            "voltage": voltage_info.get("voltage") if voltage_info else None,
            "state": voltage_info.get("state") if voltage_info else "unknown"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_motor_temperatures() -> dict:
    """Get motor thermal status.

    Returns:
        Motor temperatures and thermal protection status.
    """
    try:
        _, sensor_mgr, _ = _ensure_initialized()

        temps = await sensor_mgr.query_motor_temperatures()
        if temps:
            return {"success": True, **temps}
        return {"success": False, "error": "Failed to read motor temperatures"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_system_info() -> dict:
    """Get RVR system information.

    Returns:
        MAC address, firmware version, and uptime.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()

        return {
            "success": True,
            "mac_address": rvr_mgr.mac_address or "unknown",
            "firmware_version": rvr_mgr.firmware_version or "unknown",
            "uptime_seconds": rvr_mgr.uptime_seconds
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Safety Control Tools
# =============================================================================

@mcp.tool()
async def get_safety_status() -> dict:
    """Get safety system status.

    Returns:
        Current safety settings and state.
    """
    try:
        _, _, safety = _ensure_initialized()
        return {"success": True, **safety.get_status()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def set_speed_limit(max_speed_percent: float) -> dict:
    """Set maximum speed limit.

    Args:
        max_speed_percent: Speed limit 0-100 (percentage of max speed).

    Returns:
        New speed limit.
    """
    try:
        _, _, safety = _ensure_initialized()
        new_limit = safety.set_speed_limit(max_speed_percent)
        return {"success": True, "speed_limit_percent": new_limit}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def set_command_timeout(timeout_seconds: float) -> dict:
    """Set auto-stop timeout for movement commands.

    If no movement command is received within this time, the RVR will stop.
    Set to 0 to disable timeout.

    Args:
        timeout_seconds: Timeout in seconds (0 to disable).

    Returns:
        New timeout setting.
    """
    try:
        _, _, safety = _ensure_initialized()
        new_timeout = safety.set_timeout(timeout_seconds)
        return {
            "success": True,
            "timeout_seconds": new_timeout,
            "enabled": new_timeout > 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# IR Communication Tools
# =============================================================================

@mcp.tool()
async def send_ir_message(code: int, strength: int = 32) -> dict:
    """Send an IR message.

    Args:
        code: IR code 0-7.
        strength: Signal strength 0-64.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        from sphero_sdk import InfraredCodes

        code_map = {
            0: InfraredCodes.code_0,
            1: InfraredCodes.code_1,
            2: InfraredCodes.code_2,
            3: InfraredCodes.code_3,
            4: InfraredCodes.code_4,
            5: InfraredCodes.code_5,
            6: InfraredCodes.code_6,
            7: InfraredCodes.code_7,
        }

        ir_code = code_map.get(code)
        if ir_code is None:
            return {"success": False, "error": f"Invalid IR code: {code}. Must be 0-7."}

        await rvr_mgr.rvr.infrared_control.send_infrared_messages(
            messages=[ir_code],
            strength=max(0, min(64, strength))
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def start_ir_broadcasting(far_code: int, near_code: int) -> dict:
    """Start IR broadcasting (for robot-to-robot communication).

    Args:
        far_code: IR code for far detection 0-7.
        near_code: IR code for near detection 0-7.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await rvr_mgr.rvr.infrared_control.start_robot_to_robot_infrared_broadcasting(
            far_code=far_code,
            near_code=near_code
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def stop_ir_broadcasting() -> dict:
    """Stop IR broadcasting.

    Returns:
        Result.
    """
    try:
        rvr_mgr, _, _ = _ensure_initialized()
        rvr_mgr.ensure_connected()

        await rvr_mgr.rvr.infrared_control.stop_robot_to_robot_infrared_broadcasting()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_server() -> FastMCP:
    """Get the MCP server instance.

    Returns:
        FastMCP server instance.
    """
    return mcp
