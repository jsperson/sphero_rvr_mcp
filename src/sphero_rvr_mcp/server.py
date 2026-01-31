"""Sphero RVR MCP Server - Simplified architecture.

Features:
- Command queue for serialization
- Atomic state management
- Comprehensive observability
- Direct serial fast path for low-latency commands
"""

import asyncio
import math
from fastmcp import FastMCP

from .config import load_config_from_env
from .core.command_queue import CommandQueue
from .core.state_manager import StateManager
from .hardware.connection_manager import ConnectionManager
# Note: SensorStreamManager and SafetyMonitor require sphero_sdk
# They are not needed with DirectSerial architecture
from .observability.logging import configure_logging, get_logger

# Configure logging
config = load_config_from_env()
log_level = config.get("log_level", "INFO")
log_format = config.get("log_format", "json")
configure_logging(log_level, log_format)

logger = get_logger(__name__)


def calculate_heading_from_magnetometer(x: float, y: float) -> float:
    """Calculate compass heading from magnetometer X, Y readings.

    Args:
        x: Magnetometer X reading (points right on RVR)
        y: Magnetometer Y reading (points forward on RVR)

    Returns:
        Heading in degrees (0-360), where 0=North, 90=East, 180=South, 270=West
    """
    heading_rad = math.atan2(x, y)
    heading_deg = math.degrees(heading_rad)
    # Normalize to 0-360
    if heading_deg < 0:
        heading_deg += 360
    return heading_deg


def heading_to_cardinal(heading: float) -> str:
    """Convert heading in degrees to cardinal direction.

    Args:
        heading: Heading in degrees (0-360)

    Returns:
        Cardinal direction string (e.g., "N", "NE", "E", "SE", "S", "SW", "W", "NW")
    """
    # Define cardinal directions with their center angles
    directions = [
        ("N", 0), ("NE", 45), ("E", 90), ("SE", 135),
        ("S", 180), ("SW", 225), ("W", 270), ("NW", 315)
    ]
    # Each direction covers 45 degrees (22.5 on each side of center)
    for name, center in directions:
        diff = abs(heading - center)
        if diff > 180:
            diff = 360 - diff
        if diff <= 22.5:
            return name
    return "N"  # Fallback (shouldn't happen)


# Create FastMCP server instance
mcp = FastMCP("sphero-rvr")

# Global components (initialized once)
state_manager = StateManager()
command_queue = CommandQueue(max_queue_size=100)

# Connection manager (no RVR yet)
connection_manager = ConnectionManager(
    state_manager=state_manager,
)

# Services are disabled with DirectSerial architecture
# The tools use connection_manager.direct_serial directly
_connection_service = None
_movement_service = None
_sensor_service = None
_led_service = None
_safety_service = None
_ir_service = None

# Background tasks
_initialized = False


async def initialize_server():
    """Initialize server components."""
    global _initialized

    if _initialized:
        return

    logger.info("server_initializing")

    # Start command queue
    await command_queue.start()

    _initialized = True
    logger.info("server_initialized")


async def shutdown_server():
    """Shutdown server components."""
    logger.info("server_shutting_down")

    # Stop command queue
    await command_queue.stop()

    # Disconnect if connected
    try:
        await connection_manager.disconnect()
    except Exception as e:
        logger.warning("disconnect_on_shutdown_failed", error=str(e))

    logger.info("server_shutdown_complete")


# Initialize services after first connection
async def ensure_services_initialized():
    """Ensure services are initialized after connection.

    NOTE: With DirectSerial architecture, we bypass SDK-based services entirely.
    This function is now a no-op to avoid initialization errors.
    """
    # DirectSerial bypasses services layer - no initialization needed
    return

    # Create sensor stream manager
    sensor_manager = SensorStreamManager(
        rvr=connection_manager.rvr,
        state_manager=state_manager,
    )

    # Create safety monitor
    safety_monitor = SafetyMonitor(
        rvr=connection_manager.rvr,
        state_manager=state_manager,
    )

    # Create services
    _connection_service = ConnectionService(connection_manager)
    _movement_service = MovementService(connection_manager, command_queue, safety_monitor)
    _sensor_service = SensorService(connection_manager, sensor_manager)
    _led_service = LEDService(connection_manager, command_queue)
    _safety_service = SafetyService(safety_monitor)
    _ir_service = IRService(connection_manager, command_queue)

    logger.info("services_initialized")


def _pivot_blocking(direct_serial, degrees: float, speed: int) -> dict:
    """Blocking pivot implementation for use in executor.

    Args:
        direct_serial: DirectSerial instance
        degrees: Degrees to turn
        speed: Rotation speed 0-255

    Returns:
        Result dict
    """
    from .protocol import commands
    import time

    # Calculate target heading (0-359)
    target_heading = int(degrees) % 360

    # Step 1: Reset yaw so current direction = heading 0
    direct_serial.reset_yaw()
    time.sleep(0.15)

    # Step 2: Rotate to target heading (speed 0 = rotate only)
    direct_serial.drive_with_heading(speed, target_heading)

    # Wait for rotation (firmware handles it, use conservative estimate)
    rotation_time = abs(degrees) / 90.0 * 2.0  # Conservative: ~2s per 90 degrees
    rotation_time = max(0.5, min(rotation_time, 15.0))
    time.sleep(rotation_time)

    # Step 3: Reset yaw again so new direction = heading 0
    direct_serial.reset_yaw()
    time.sleep(0.1)

    # Step 4: Stop with raw motors off (avoids heading correction)
    direct_serial._send(commands.raw_motors(0, 0, 0, 0))

    return {
        "success": True,
        "degrees": degrees,
        "target_heading": target_heading,
        "rotation_time": rotation_time,
    }


# Register all tools
def register_tools():
    """Register all MCP tools.

    This creates wrapper functions that initialize services on first call.
    """

    # Connection tools
    @mcp.tool()
    async def test_immediate_return() -> dict:
        """Test tool that returns immediately."""
        return {"success": True, "message": "Immediate return works"}

    @mcp.tool()
    async def test_slow_return() -> dict:
        """Test tool that takes 3 seconds."""
        import time
        with open("/tmp/rvr_test_slow.log", "a") as f:
            f.write(f"{time.time()} Test slow starting\n")
            f.flush()
        await asyncio.sleep(3)
        with open("/tmp/rvr_test_slow.log", "a") as f:
            f.write(f"{time.time()} Test slow returning\n")
            f.flush()
        return {"success": True, "message": "Slow return after 3 seconds"}

    @mcp.tool()
    async def connect_simple() -> dict:
        """Simple connect test without parameters."""
        import time
        with open("/tmp/rvr_connect_simple.log", "a") as f:
            f.write(f"{time.time()} connect_simple called\n")
            f.flush()
        return {"success": True, "message": "Simple connect works"}

    @mcp.tool()
    async def connect(port: str = "/dev/ttyAMA0", baud: int = 115200) -> dict:
        """Connect to the Sphero RVR robot and wake it up."""
        import time
        with open("/tmp/rvr_mcp_debug.log", "a") as f:
            f.write(f"{time.time()} TOOL_CONNECT_CALLED port={port} baud={baud}\n")
            f.flush()
        logger.info("TOOL_CONNECT_CALLED", port=port, baud=baud)

        # Direct connection - bypass service layer entirely
        try:
            with open("/tmp/rvr_mcp_debug.log", "a") as f:
                f.write(f"{time.time()} TOOL_CONNECT_STARTING_AWAIT\n")
                f.flush()
            logger.info("TOOL_CONNECT_STARTING_AWAIT")
            result = await asyncio.wait_for(
                connection_manager.connect(port, baud),
                timeout=10.0  # 10 second timeout
            )
            with open("/tmp/rvr_mcp_debug.log", "a") as f:
                f.write(f"{time.time()} TOOL_CONNECT_COMPLETED result={result}\n")
                f.flush()
            logger.info("TOOL_CONNECT_COMPLETED", result=result)
            with open("/tmp/rvr_mcp_debug.log", "a") as f:
                f.write(f"{time.time()} TOOL_CONNECT_RETURNING\n")
                f.flush()
            logger.info("TOOL_CONNECT_RETURNING")
            return result
        except asyncio.TimeoutError:
            logger.error("connection_timeout", port=port, timeout_seconds=10)
            # Force cleanup on timeout
            try:
                await connection_manager.disconnect()
            except Exception as e:
                logger.warning("cleanup_after_timeout_failed", error=str(e))
            logger.info("TOOL_CONNECT_TIMEOUT_RETURNING")
            return {
                "success": False,
                "error": "Connection timed out after 10 seconds"
            }
        except Exception as e:
            logger.error("connection_exception", error=str(e), error_type=type(e).__name__)
            logger.info("TOOL_CONNECT_EXCEPTION_RETURNING")
            return {
                "success": False,
                "error": f"Connection failed: {str(e)}"
            }

    @mcp.tool()
    async def disconnect() -> dict:
        """Disconnect from RVR."""
        try:
            await connection_manager.disconnect()
            return {"success": True, "message": "Disconnected"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    async def get_connection_status() -> dict:
        """Get connection status."""
        is_connected = (
            connection_manager.direct_serial is not None
            and connection_manager.direct_serial.is_connected
        )
        system_snapshot = await state_manager.system_state.snapshot()
        connection_snapshot = await state_manager.connection_info.snapshot()
        return {
            "success": True,
            "connected": is_connected,
            "connection_state": system_snapshot.get("connection_state"),
            "serial_port": connection_snapshot.get("serial_port"),
            "baud_rate": connection_snapshot.get("baud_rate"),
            "uptime_seconds": connection_snapshot.get("uptime_seconds"),
        }

    # Movement tools
    @mcp.tool()
    async def drive_with_heading(speed: int, heading: int, reverse: bool = False) -> dict:
        """Drive at speed toward heading."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.drive_with_heading(speed, heading, reverse)
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _movement_service.drive_with_heading(speed, heading, reverse)

    @mcp.tool()
    async def drive_tank(left_velocity: float, right_velocity: float) -> dict:
        """Drive with tank controls."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # Check emergency stop
        if await state_manager.safety_state.is_emergency_stopped():
            return {"success": False, "error": "Emergency stop is active"}

        ok = connection_manager.direct_serial.drive_tank(left_velocity, right_velocity)
        return {"success": ok}

    @mcp.tool()
    async def drive_rc(linear_velocity: float, yaw_velocity: float) -> dict:
        """Drive with RC controls."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # Check emergency stop
        if await state_manager.safety_state.is_emergency_stopped():
            return {"success": False, "error": "Emergency stop is active"}

        ok = connection_manager.direct_serial.drive_rc(linear_velocity, yaw_velocity)
        return {"success": ok}

    @mcp.tool()
    async def stop() -> dict:
        """Stop RVR."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.stop()
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _movement_service.stop()

    @mcp.tool()
    async def emergency_stop() -> dict:
        """Emergency stop."""
        # Set emergency stop flag
        await state_manager.safety_state.set_emergency_stop(True)

        # Stop the robot if connected
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            connection_manager.direct_serial.stop()

        return {"success": True, "message": "Emergency stop activated"}

    @mcp.tool()
    async def clear_emergency_stop() -> dict:
        """Clear emergency stop."""
        await state_manager.safety_state.set_emergency_stop(False)
        return {"success": True, "message": "Emergency stop cleared"}

    @mcp.tool()
    async def reset_yaw() -> dict:
        """Reset yaw."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.reset_yaw()
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _movement_service.reset_yaw()

    @mcp.tool()
    async def reset_locator() -> dict:
        """Reset locator."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.reset_locator()
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _movement_service.reset_locator()

    @mcp.tool()
    async def pivot(degrees: float, speed: int = 0) -> dict:
        """Pivot (turn in place) by a specified number of degrees.

        Rotates the RVR without forward motion. Uses internal heading
        control for accurate turning.

        Args:
            degrees: Degrees to turn. Positive = turn right (clockwise),
                     negative = turn left (counter-clockwise).
            speed: Rotation speed 0-255 (0 = let RVR control rotation speed).

        Returns:
            Result with degrees turned.
        """
        # Use direct serial for reliable pivot
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected (direct serial)"}

        # Check emergency stop
        if await state_manager.safety_state.is_emergency_stopped():
            return {"success": False, "error": "Emergency stop is active"}

        # Run the blocking pivot operation in an executor
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                _pivot_blocking,
                connection_manager.direct_serial,
                degrees,
                speed
            )
            return result
        except Exception as e:
            logger.error("pivot_error", error=str(e))
            return {"success": False, "error": str(e)}


    @mcp.tool()
    async def drive_forward(
        distance: float,
        speed: float = 0.5,
    ) -> dict:
        """Drive forward a specified distance in meters.

        Uses RVR's internal position controller for accurate movement.

        Args:
            distance: Distance to travel in meters.
            speed: Speed in m/s (default: 0.5, max: ~1.5).

        Returns:
            Result with distance traveled.
        """
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # Check emergency stop
        if await state_manager.safety_state.is_emergency_stopped():
            return {"success": False, "error": "Emergency stop is active"}

        # Run blocking movement call in executor to not block the event loop
        loop = asyncio.get_event_loop()
        try:
            ok = await loop.run_in_executor(
                None,
                connection_manager.direct_serial.drive_forward_meters,
                distance,
                speed
            )
            return {"success": ok, "distance": distance}
        except Exception as e:
            logger.error("drive_forward_error", error=str(e))
            return {"success": False, "error": str(e)}

    @mcp.tool()
    async def drive_backward(
        distance: float,
        speed: float = 0.5,
    ) -> dict:
        """Drive backward a specified distance in meters.

        Uses RVR's internal position controller for accurate movement.

        Args:
            distance: Distance to travel in meters.
            speed: Speed in m/s (default: 0.5, max: ~1.5).

        Returns:
            Result with distance traveled.
        """
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # Check emergency stop
        if await state_manager.safety_state.is_emergency_stopped():
            return {"success": False, "error": "Emergency stop is active"}

        # Run blocking movement call in executor to not block the event loop
        loop = asyncio.get_event_loop()
        try:
            ok = await loop.run_in_executor(
                None,
                connection_manager.direct_serial.drive_backward_meters,
                distance,
                speed
            )
            return {"success": ok, "distance": distance}
        except Exception as e:
            logger.error("drive_backward_error", error=str(e))
            return {"success": False, "error": str(e)}

    # LED tools
    @mcp.tool()
    async def set_all_leds(red: int, green: int, blue: int) -> dict:
        """Set all LEDs."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.set_all_leds(red, green, blue)
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _led_service.set_all_leds(red, green, blue)

    @mcp.tool()
    async def set_led(led_group: str, red: int, green: int, blue: int) -> dict:
        """Set specific LED group."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # Valid LED group names
        valid_groups = [
            "headlight_left", "headlight_right",
            "battery_door_front", "battery_door_rear",
            "power_button_front", "power_button_rear",
            "brakelight_left", "brakelight_right",
            "status_indication_left", "status_indication_right",
        ]

        if led_group not in valid_groups:
            return {
                "success": False,
                "error": f"Invalid LED group: {led_group}. Valid groups: {valid_groups}",
            }

        ok = connection_manager.direct_serial.set_led_group(led_group, red, green, blue)
        return {"success": ok, "led_group": led_group}

    @mcp.tool()
    async def turn_leds_off() -> dict:
        """Turn off all LEDs."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.set_all_leds(0, 0, 0)
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _led_service.turn_leds_off()

    # Sensor tools
    @mcp.tool()
    async def start_sensor_streaming(sensors: list, interval_ms: int = 250) -> dict:
        """Start sensor streaming."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # Valid sensors for polling-based streaming
        valid_sensors = ["battery", "ambient_light", "color"]

        # Validate requested sensors
        invalid = [s for s in sensors if s not in valid_sensors]
        if invalid:
            return {
                "success": False,
                "error": f"Invalid sensors: {invalid}. Valid: {valid_sensors}",
            }

        # Update streaming state
        await state_manager.sensor_state.set_streaming(
            active=True,
            sensors=sensors,
            interval_ms=interval_ms,
        )

        return {
            "success": True,
            "message": "Sensor streaming configured (polling mode)",
            "sensors": sensors,
            "interval_ms": interval_ms,
        }

    @mcp.tool()
    async def stop_sensor_streaming() -> dict:
        """Stop sensor streaming."""
        await state_manager.sensor_state.set_streaming(active=False, sensors=[])
        await state_manager.sensor_state.clear_cache()
        return {"success": True, "message": "Sensor streaming stopped"}

    @mcp.tool()
    async def get_sensor_data(sensors: list = None) -> dict:
        """Get sensor data."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # If no sensors specified, use streaming sensors or default
        if sensors is None:
            sensor_snapshot = await state_manager.sensor_state.snapshot()
            sensors = sensor_snapshot.get("streaming_sensors", [])
            if not sensors:
                sensors = ["battery", "ambient_light", "color"]

        result = {"success": True, "sensors": {}}

        # Poll each requested sensor
        for sensor in sensors:
            if sensor == "battery":
                value = connection_manager.direct_serial.get_battery_percentage()
                if value is not None:
                    result["sensors"]["battery"] = {"percentage": value}

            elif sensor == "ambient_light":
                value = connection_manager.direct_serial.get_ambient_light()
                if value is not None:
                    result["sensors"]["ambient_light"] = {"value": value}

            elif sensor == "color":
                value = connection_manager.direct_serial.get_rgbc_sensor_values()
                if value is not None:
                    result["sensors"]["color"] = value

        return result

    @mcp.tool()
    async def get_ambient_light() -> dict:
        """Get ambient light."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        light_value = connection_manager.direct_serial.get_ambient_light()
        if light_value is not None:
            return {"success": True, "ambient_light": light_value}
        return {"success": False, "error": "Failed to read ambient light sensor"}

    @mcp.tool()
    async def enable_color_detection(enabled: bool = True) -> dict:
        """Enable color detection."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.enable_color_detection(enabled)
        return {"success": ok, "enabled": enabled}

    @mcp.tool()
    async def get_color_detection(stabilization_ms: int = 50) -> dict:
        """Get color detection."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        # Turn on belly LED
        if not connection_manager.direct_serial.enable_color_detection(True):
            return {"success": False, "error": "Failed to enable color detection LED"}

        # Stabilization delay for LED to illuminate surface
        if stabilization_ms > 0:
            await asyncio.sleep(stabilization_ms / 1000.0)

        result = None

        # Try get_current_detected_color first (returns classified color)
        color = connection_manager.direct_serial.get_current_detected_color()
        if color is not None:
            result = {
                "success": True,
                "red": color["red"],
                "green": color["green"],
                "blue": color["blue"],
                "confidence": color["confidence"],
                "color_classification_id": color["color_classification_id"],
            }
        else:
            # Fallback to raw RGBC sensor values
            rgbc = connection_manager.direct_serial.get_rgbc_sensor_values()
            if rgbc is not None:
                result = {
                    "success": True,
                    "red": rgbc["red"],
                    "green": rgbc["green"],
                    "blue": rgbc["blue"],
                    "clear": rgbc["clear"],
                }

        # Turn off belly LED
        connection_manager.direct_serial.enable_color_detection(False)

        if result is not None:
            return result
        return {"success": False, "error": "Failed to read color sensor"}

    @mcp.tool()
    async def get_battery_status() -> dict:
        """Get battery status."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        percentage = connection_manager.direct_serial.get_battery_percentage()
        if percentage is not None:
            return {"success": True, "battery_percentage": percentage}
        return {"success": False, "error": "Failed to read battery status"}

    # Safety tools
    @mcp.tool()
    async def get_safety_status() -> dict:
        """Get safety status."""
        safety_snapshot = await state_manager.safety_state.snapshot()
        return {"success": True, **safety_snapshot}

    @mcp.tool()
    async def set_speed_limit(max_speed_percent: float) -> dict:
        """Set speed limit."""
        await state_manager.safety_state.set_speed_limit(max_speed_percent)
        current_limit = await state_manager.safety_state.get_speed_limit()
        return {"success": True, "speed_limit_percent": current_limit}

    @mcp.tool()
    async def set_command_timeout(timeout_seconds: float) -> dict:
        """Set command timeout."""
        await state_manager.safety_state.set_command_timeout(timeout_seconds)
        current_timeout = await state_manager.safety_state.get_command_timeout()
        return {"success": True, "command_timeout_seconds": current_timeout}

    # IR tools
    @mcp.tool()
    async def send_ir_message(code: int, strength: int = 32) -> dict:
        """Send IR message."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.send_ir_message(code, strength)
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _ir_service.send_ir_message(code, strength)

    @mcp.tool()
    async def start_ir_broadcasting(far_code: int, near_code: int) -> dict:
        """Start IR broadcasting."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.start_ir_broadcasting(far_code, near_code)
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _ir_service.start_ir_broadcasting(far_code, near_code)

    @mcp.tool()
    async def stop_ir_broadcasting() -> dict:
        """Stop IR broadcasting."""
        # Fast path: direct serial
        if connection_manager.direct_serial and connection_manager.direct_serial.is_connected:
            ok = connection_manager.direct_serial.stop_ir_broadcasting()
            return {"success": ok}
        # Fallback: SDK path
        await ensure_services_initialized()
        return await _ir_service.stop_ir_broadcasting()

    # ========================================================================
    # Phase 1: Temperature Sensors
    # ========================================================================

    @mcp.tool()
    async def get_temperature() -> dict:
        """Get temperature sensor readings (motor and Nordic die temps).

        Returns temperatures in Celsius for left_motor, right_motor, and nordic_die.
        """
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        temps = connection_manager.direct_serial.get_temperature()
        if temps is not None:
            return {"success": True, **temps}
        return {"success": False, "error": "Failed to read temperature sensors"}

    @mcp.tool()
    async def get_motor_thermal_protection_status() -> dict:
        """Get motor thermal protection status.

        Returns temperature and status for each motor.
        Status: 0=ok, 1=warning, 2=critical
        """
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        status = connection_manager.direct_serial.get_thermal_protection_status()
        if status is not None:
            # Add human-readable status names
            status_names = {0: 'ok', 1: 'warning', 2: 'critical'}
            status['left_status_name'] = status_names.get(status['left_status'], 'unknown')
            status['right_status_name'] = status_names.get(status['right_status'], 'unknown')
            return {"success": True, **status}
        return {"success": False, "error": "Failed to read thermal protection status"}

    # ========================================================================
    # Phase 2: System Information
    # ========================================================================

    @mcp.tool()
    async def get_firmware_version() -> dict:
        """Get firmware version (major.minor.revision) for both processors."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        result = {"success": True}

        # Get Nordic (BT) firmware version
        nordic = connection_manager.direct_serial.get_firmware_version(target=0x01)
        if nordic:
            result["nordic"] = nordic
            result["nordic_version"] = f"{nordic['major']}.{nordic['minor']}.{nordic['revision']}"

        # Get ST MCU firmware version
        mcu = connection_manager.direct_serial.get_firmware_version(target=0x02)
        if mcu:
            result["mcu"] = mcu
            result["mcu_version"] = f"{mcu['major']}.{mcu['minor']}.{mcu['revision']}"

        if "nordic" not in result and "mcu" not in result:
            return {"success": False, "error": "Failed to read firmware version"}

        return result

    @mcp.tool()
    async def get_mac_address() -> dict:
        """Get Bluetooth MAC address."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        mac = connection_manager.direct_serial.get_mac_address()
        if mac is not None:
            return {"success": True, "mac_address": mac}
        return {"success": False, "error": "Failed to read MAC address"}

    @mcp.tool()
    async def get_board_revision() -> dict:
        """Get PCB board revision for both processors."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        result = {"success": True}

        nordic_rev = connection_manager.direct_serial.get_board_revision(target=0x01)
        if nordic_rev is not None:
            result["nordic_revision"] = nordic_rev

        mcu_rev = connection_manager.direct_serial.get_board_revision(target=0x02)
        if mcu_rev is not None:
            result["mcu_revision"] = mcu_rev

        if "nordic_revision" not in result and "mcu_revision" not in result:
            return {"success": False, "error": "Failed to read board revision"}

        return result

    @mcp.tool()
    async def get_processor_name() -> dict:
        """Get processor identifier strings for both processors."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        result = {"success": True}

        nordic_name = connection_manager.direct_serial.get_processor_name(target=0x01)
        if nordic_name:
            result["nordic_processor"] = nordic_name

        mcu_name = connection_manager.direct_serial.get_processor_name(target=0x02)
        if mcu_name:
            result["mcu_processor"] = mcu_name

        if "nordic_processor" not in result and "mcu_processor" not in result:
            return {"success": False, "error": "Failed to read processor name"}

        return result

    @mcp.tool()
    async def get_sku() -> dict:
        """Get product SKU string."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        sku = connection_manager.direct_serial.get_sku()
        if sku is not None:
            return {"success": True, "sku": sku}
        return {"success": False, "error": "Failed to read SKU"}

    @mcp.tool()
    async def get_core_uptime() -> dict:
        """Get core uptime in milliseconds since power-on for both processors."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        result = {"success": True}

        nordic_uptime = connection_manager.direct_serial.get_core_uptime(target=0x01)
        if nordic_uptime is not None:
            result["nordic_uptime_ms"] = nordic_uptime
            result["nordic_uptime_seconds"] = nordic_uptime / 1000.0

        mcu_uptime = connection_manager.direct_serial.get_core_uptime(target=0x02)
        if mcu_uptime is not None:
            result["mcu_uptime_ms"] = mcu_uptime
            result["mcu_uptime_seconds"] = mcu_uptime / 1000.0

        if "nordic_uptime_ms" not in result and "mcu_uptime_ms" not in result:
            return {"success": False, "error": "Failed to read uptime"}

        return result

    # ========================================================================
    # Phase 3: Extended Battery Info
    # ========================================================================

    @mcp.tool()
    async def get_battery_voltage() -> dict:
        """Get battery voltage in volts (calibrated)."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        voltage = connection_manager.direct_serial.get_battery_voltage()
        if voltage is not None:
            return {"success": True, "voltage": voltage}
        return {"success": False, "error": "Failed to read battery voltage"}

    @mcp.tool()
    async def get_battery_voltage_state() -> dict:
        """Get battery voltage state (ok/low/critical)."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        state = connection_manager.direct_serial.get_battery_voltage_state()
        if state is not None:
            return {"success": True, **state}
        return {"success": False, "error": "Failed to read battery voltage state"}

    @mcp.tool()
    async def get_battery_thresholds() -> dict:
        """Get battery voltage thresholds (critical, low, hysteresis)."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        thresholds = connection_manager.direct_serial.get_battery_thresholds()
        if thresholds is not None:
            return {"success": True, **thresholds}
        return {"success": False, "error": "Failed to read battery thresholds"}

    # ========================================================================
    # Phase 4: Motion Sensors (Point Reads)
    # ========================================================================

    @mcp.tool()
    async def get_encoder_counts() -> dict:
        """Get wheel encoder tick counts (left and right)."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        counts = connection_manager.direct_serial.get_encoder_counts()
        if counts is not None:
            return {"success": True, **counts}
        return {"success": False, "error": "Failed to read encoder counts"}

    @mcp.tool()
    async def get_magnetometer() -> dict:
        """Get magnetometer X, Y, Z readings with heading and cardinal direction."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        mag = connection_manager.direct_serial.get_magnetometer()
        if mag is not None:
            # Calculate heading and cardinal direction from X, Y
            heading = calculate_heading_from_magnetometer(mag['x'], mag['y'])
            cardinal = heading_to_cardinal(heading)
            return {
                "success": True,
                **mag,
                "heading": round(heading, 1),
                "cardinal": cardinal
            }
        return {"success": False, "error": "Failed to read magnetometer"}

    @mcp.tool()
    async def calibrate_magnetometer() -> dict:
        """Start magnetometer calibration (calibrate to north).

        This is an async operation - the RVR will notify when complete.
        Rotate the RVR 360 degrees during calibration.
        """
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.calibrate_magnetometer()
        if ok:
            return {
                "success": True,
                "message": "Magnetometer calibration started. Rotate RVR 360 degrees.",
            }
        return {"success": False, "error": "Failed to start magnetometer calibration"}

    # ========================================================================
    # Phase 5: Motor Protection
    # ========================================================================

    @mcp.tool()
    async def get_motor_fault_state() -> dict:
        """Check if motor fault is currently active."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        is_fault = connection_manager.direct_serial.get_motor_fault_state()
        if is_fault is not None:
            return {"success": True, "is_fault": is_fault}
        return {"success": False, "error": "Failed to read motor fault state"}

    @mcp.tool()
    async def enable_motor_stall_notify(enabled: bool = True) -> dict:
        """Enable or disable motor stall detection notifications."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.enable_motor_stall_notify(enabled)
        return {"success": ok, "enabled": enabled}

    @mcp.tool()
    async def enable_motor_fault_notify(enabled: bool = True) -> dict:
        """Enable or disable motor fault detection notifications."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.enable_motor_fault_notify(enabled)
        return {"success": ok, "enabled": enabled}

    # ========================================================================
    # Phase 6: IR Follow/Evade
    # ========================================================================

    @mcp.tool()
    async def start_ir_following(far_code: int, near_code: int) -> dict:
        """Start following an IR-broadcasting robot.

        Args:
            far_code: IR code to follow when far (0-7)
            near_code: IR code to follow when near (0-7)
        """
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.start_ir_following(far_code, near_code)
        return {"success": ok, "far_code": far_code, "near_code": near_code}

    @mcp.tool()
    async def stop_ir_following() -> dict:
        """Stop IR following behavior."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.stop_ir_following()
        return {"success": ok}

    @mcp.tool()
    async def start_ir_evading(far_code: int, near_code: int) -> dict:
        """Start evading an IR-broadcasting robot.

        Args:
            far_code: IR code to evade when far (0-7)
            near_code: IR code to evade when near (0-7)
        """
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.start_ir_evading(far_code, near_code)
        return {"success": ok, "far_code": far_code, "near_code": near_code}

    @mcp.tool()
    async def stop_ir_evading() -> dict:
        """Stop IR evading behavior."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        ok = connection_manager.direct_serial.stop_ir_evading()
        return {"success": ok}

    @mcp.tool()
    async def get_ir_readings() -> dict:
        """Get all 4 IR sensor readings (front_left, front_right, back_right, back_left)."""
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected"}

        readings = connection_manager.direct_serial.get_ir_readings()
        if readings is not None:
            return {"success": True, **readings}
        return {"success": False, "error": "Failed to read IR sensors"}


# Register tools on module load
register_tools()


def get_server():
    """Get the MCP server instance.

    Returns:
        FastMCP server instance
    """
    return mcp
