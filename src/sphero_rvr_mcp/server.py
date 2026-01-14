"""Sphero RVR MCP Server - New architecture.

This is a complete rewrite with:
- Command queue for serialization
- Circuit breaker for resilience
- Event bus for sensor distribution
- Atomic state management
- Comprehensive observability
"""

import asyncio
from fastmcp import FastMCP

from .config import load_config_from_env
from .core.command_queue import CommandQueue
from .core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .core.event_bus import EventBus
from .core.state_manager import StateManager
from .hardware.connection_manager import ConnectionManager
from .hardware.sensor_stream_manager import SensorStreamManager
from .hardware.safety_monitor import SafetyMonitor
from .services.connection_service import ConnectionService
from .services.movement_service import MovementService
from .services.sensor_service import SensorService
from .services.led_service import LEDService
from .services.safety_service import SafetyService
from .services.ir_service import IRService
from .tools.connection_tools import register_connection_tools
from .tools.movement_tools import register_movement_tools
from .tools.led_tools import register_led_tools
from .tools.sensor_tools import register_sensor_tools
from .tools.safety_tools import register_safety_tools
from .tools.ir_tools import register_ir_tools
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
circuit_breaker = CircuitBreaker(CircuitBreakerConfig())
command_queue = CommandQueue(max_queue_size=100)
event_bus = EventBus(max_queue_size=1000)

# Connection manager (no RVR yet)
connection_manager = ConnectionManager(
    state_manager=state_manager,
    circuit_breaker=circuit_breaker,
)

# Services (will be initialized after connection)
_connection_service: ConnectionService = None
_movement_service: MovementService = None
_sensor_service: SensorService = None
_led_service: LEDService = None
_safety_service: SafetyService = None
_ir_service: IRService = None

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

    # Start event bus
    await event_bus.start()

    _initialized = True
    logger.info("server_initialized")


async def shutdown_server():
    """Shutdown server components."""
    logger.info("server_shutting_down")

    # Stop command queue
    await command_queue.stop()

    # Stop event bus
    await event_bus.stop()

    # Disconnect if connected
    try:
        await connection_manager.disconnect()
    except Exception as e:
        logger.warning("disconnect_on_shutdown_failed", error=str(e))

    logger.info("server_shutdown_complete")


# Initialize services after first connection
async def ensure_services_initialized():
    """Ensure services are initialized after connection."""
    global _connection_service, _movement_service, _sensor_service
    global _led_service, _safety_service, _ir_service

    if _connection_service is not None:
        return  # Already initialized

    # Check if connected
    await connection_manager.ensure_connected()

    # Create sensor stream manager
    sensor_manager = SensorStreamManager(
        rvr=connection_manager.rvr,
        state_manager=state_manager,
        event_bus=event_bus,
    )

    # Create safety monitor
    safety_monitor = SafetyMonitor(
        rvr=connection_manager.rvr,
        state_manager=state_manager,
        event_bus=event_bus,
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
    async def connect(port: str = "/dev/ttyS0", baud: int = 115200) -> dict:
        """Connect to the Sphero RVR robot."""
        await initialize_server()

        global _connection_service
        if _connection_service is None:
            _connection_service = ConnectionService(connection_manager)

        result = await _connection_service.connect(port, baud)

        if result.get("success"):
            # Initialize other services now that we're connected
            await ensure_services_initialized()

        return result

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
        await ensure_services_initialized()
        return await _movement_service.reset_yaw()

    @mcp.tool()
    async def reset_locator() -> dict:
        """Reset locator."""
        await ensure_services_initialized()
        return await _movement_service.reset_locator()

    # LED tools
    @mcp.tool()
    async def set_all_leds(red: int, green: int, blue: int) -> dict:
        """Set all LEDs."""
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
        await ensure_services_initialized()
        return await _ir_service.send_ir_message(code, strength)

    @mcp.tool()
    async def start_ir_broadcasting(far_code: int, near_code: int) -> dict:
        """Start IR broadcasting."""
        await ensure_services_initialized()
        return await _ir_service.start_ir_broadcasting(far_code, near_code)

    @mcp.tool()
    async def stop_ir_broadcasting() -> dict:
        """Stop IR broadcasting."""
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
