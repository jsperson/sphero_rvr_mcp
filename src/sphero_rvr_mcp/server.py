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
        if _connection_service is None:
            return {"success": False, "error": "Not connected"}
        return await _connection_service.disconnect()

    @mcp.tool()
    async def get_connection_status() -> dict:
        """Get connection status."""
        if _connection_service is None:
            return {"success": False, "error": "Not connected"}
        return await _connection_service.get_connection_status()

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
        await ensure_services_initialized()
        return await _movement_service.drive_tank(left_velocity, right_velocity)

    @mcp.tool()
    async def drive_rc(linear_velocity: float, yaw_velocity: float) -> dict:
        """Drive with RC controls."""
        await ensure_services_initialized()
        return await _movement_service.drive_rc(linear_velocity, yaw_velocity)

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
        await ensure_services_initialized()
        return await _movement_service.emergency_stop()

    @mcp.tool()
    async def clear_emergency_stop() -> dict:
        """Clear emergency stop."""
        await ensure_services_initialized()
        return await _movement_service.clear_emergency_stop()

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
        await ensure_services_initialized()
        return await _led_service.set_led(led_group, red, green, blue)

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
        await ensure_services_initialized()
        return await _sensor_service.start_sensor_streaming(sensors, interval_ms)

    @mcp.tool()
    async def stop_sensor_streaming() -> dict:
        """Stop sensor streaming."""
        await ensure_services_initialized()
        return await _sensor_service.stop_sensor_streaming()

    @mcp.tool()
    async def get_sensor_data(sensors: list = None) -> dict:
        """Get sensor data."""
        await ensure_services_initialized()
        return await _sensor_service.get_sensor_data(sensors)

    @mcp.tool()
    async def get_ambient_light() -> dict:
        """Get ambient light."""
        await ensure_services_initialized()
        return await _sensor_service.get_ambient_light()

    @mcp.tool()
    async def enable_color_detection(enabled: bool = True) -> dict:
        """Enable color detection."""
        await ensure_services_initialized()
        return await _sensor_service.enable_color_detection(enabled)

    @mcp.tool()
    async def get_color_detection(stabilization_ms: int = 50) -> dict:
        """Get color detection."""
        await ensure_services_initialized()
        return await _sensor_service.get_color_detection(stabilization_ms)

    @mcp.tool()
    async def get_battery_status() -> dict:
        """Get battery status."""
        await ensure_services_initialized()
        return await _sensor_service.get_battery_status()

    # Safety tools
    @mcp.tool()
    async def get_safety_status() -> dict:
        """Get safety status."""
        await ensure_services_initialized()
        return await _safety_service.get_safety_status()

    @mcp.tool()
    async def set_speed_limit(max_speed_percent: float) -> dict:
        """Set speed limit."""
        await ensure_services_initialized()
        return await _safety_service.set_speed_limit(max_speed_percent)

    @mcp.tool()
    async def set_command_timeout(timeout_seconds: float) -> dict:
        """Set command timeout."""
        await ensure_services_initialized()
        return await _safety_service.set_command_timeout(timeout_seconds)

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
