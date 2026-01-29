"""Sphero RVR MCP Server - Simplified architecture.

Features:
- Command queue for serialization
- Atomic state management
- Comprehensive observability
- Direct serial fast path for low-latency commands
"""

import asyncio
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
        import asyncio

        # Use direct serial for reliable pivot
        if not connection_manager.direct_serial or not connection_manager.direct_serial.is_connected:
            return {"success": False, "error": "Not connected (direct serial)"}

        # Calculate target heading (0-359)
        # Positive degrees = right = positive heading
        # Negative degrees = left = needs to wrap (e.g., -90 = 270)
        target_heading = int(degrees) % 360

        # Step 1: Reset yaw so current direction = heading 0
        connection_manager.direct_serial.reset_yaw()
        await asyncio.sleep(0.15)

        # Step 2: Rotate to target heading (speed 0 = rotate only)
        connection_manager.direct_serial.drive_with_heading(speed, target_heading)

        # Wait for rotation (firmware handles it, use conservative estimate)
        # The RVR's firmware uses its internal magnetometer for closed-loop control
        rotation_time = abs(degrees) / 90.0 * 2.0  # Conservative: ~2s per 90 degrees
        rotation_time = max(0.5, min(rotation_time, 15.0))
        await asyncio.sleep(rotation_time)

        # Step 3: Reset yaw again so new direction = heading 0
        connection_manager.direct_serial.reset_yaw()
        await asyncio.sleep(0.1)

        # Step 4: Stop with raw motors off (avoids heading correction)
        from .protocol import commands
        connection_manager.direct_serial._send(commands.raw_motors(0, 0, 0, 0))

        return {
            "success": True,
            "degrees": degrees,
            "target_heading": target_heading,
            "rotation_time": rotation_time,
        }

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

        ok = connection_manager.direct_serial.drive_forward_meters(distance, speed)
        return {"success": ok, "distance": distance}

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

        ok = connection_manager.direct_serial.drive_backward_meters(distance, speed)
        return {"success": ok, "distance": distance}

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


# Register tools on module load
register_tools()


def get_server():
    """Get the MCP server instance.

    Returns:
        FastMCP server instance
    """
    return mcp
