"""Direct API for Sphero RVR - bypasses MCP for testing/scripting.

This module provides direct access to RVR functionality without going through
the MCP protocol. Useful for testing and standalone scripts.
"""

import asyncio
from typing import Optional

from .core.command_queue import CommandQueue
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
from .observability.logging import configure_logging, get_logger


class RVRClient:
    """Direct client for Sphero RVR - no MCP required.

    Usage:
        client = RVRClient()
        await client.initialize()
        await client.connect()
        await client.set_all_leds(255, 165, 0)  # Orange!
        await client.disconnect()
        await client.shutdown()
    """

    def __init__(self, log_level: str = "INFO", log_format: str = "console"):
        """Initialize RVR client.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_format: Log format (json or console)
        """
        # Configure logging
        configure_logging(log_level, log_format)
        self.logger = get_logger(__name__)

        # Core components
        self.state_manager = StateManager()
        self.command_queue = CommandQueue(max_queue_size=100)

        # Hardware managers
        self.connection_manager = ConnectionManager(
            state_manager=self.state_manager,
        )

        # Services (created after connection)
        self._connection_service: Optional[ConnectionService] = None
        self._movement_service: Optional[MovementService] = None
        self._sensor_service: Optional[SensorService] = None
        self._led_service: Optional[LEDService] = None
        self._safety_service: Optional[SafetyService] = None
        self._ir_service: Optional[IRService] = None

        self._initialized = False
        self._connected = False

    async def initialize(self):
        """Initialize background tasks."""
        if self._initialized:
            return

        self.logger.info("Initializing RVR client...")

        # Start command queue
        await self.command_queue.start()

        self._initialized = True
        self.logger.info("RVR client initialized")

    async def connect(self, port: str = "/dev/ttyS0", baud_rate: int = 115200) -> dict:
        """Connect to RVR.

        Args:
            port: Serial port path
            baud_rate: Baud rate

        Returns:
            Connection result
        """
        if not self._initialized:
            await self.initialize()

        # Create connection service
        self._connection_service = ConnectionService(self.connection_manager)

        # Connect
        result = await self._connection_service.connect(port, baud_rate)

        if result.get("success"):
            self._connected = True

            # Initialize other services
            sensor_manager = SensorStreamManager(
                rvr=self.connection_manager.rvr,
                state_manager=self.state_manager,
            )

            safety_monitor = SafetyMonitor(
                rvr=self.connection_manager.rvr,
                state_manager=self.state_manager,
            )

            self._movement_service = MovementService(
                self.connection_manager, self.command_queue, safety_monitor
            )
            self._sensor_service = SensorService(
                self.connection_manager, sensor_manager
            )
            self._led_service = LEDService(
                self.connection_manager, self.command_queue
            )
            self._safety_service = SafetyService(safety_monitor)
            self._ir_service = IRService(
                self.connection_manager, self.command_queue
            )

            self.logger.info("Services initialized")

        return result

    async def disconnect(self) -> dict:
        """Disconnect from RVR."""
        if self._connection_service:
            result = await self._connection_service.disconnect()
            self._connected = False
            return result
        return {"success": True, "message": "Not connected"}

    async def shutdown(self):
        """Shutdown client and cleanup."""
        if self._connected:
            await self.disconnect()

        if self._initialized:
            await self.command_queue.stop()
            self._initialized = False
            self.logger.info("RVR client shutdown")

    # Connection methods
    async def get_connection_status(self) -> dict:
        """Get connection status."""
        if self._connection_service:
            return await self._connection_service.get_connection_status()
        return {"success": False, "error": "Not connected"}

    # LED methods
    async def set_all_leds(self, red: int, green: int, blue: int) -> dict:
        """Set all LEDs to same color."""
        if not self._led_service:
            return {"success": False, "error": "Not connected"}
        return await self._led_service.set_all_leds(red, green, blue)

    async def set_led(self, led_group: str, red: int, green: int, blue: int) -> dict:
        """Set specific LED group."""
        if not self._led_service:
            return {"success": False, "error": "Not connected"}
        return await self._led_service.set_led(led_group, red, green, blue)

    async def turn_leds_off(self) -> dict:
        """Turn off all LEDs."""
        if not self._led_service:
            return {"success": False, "error": "Not connected"}
        return await self._led_service.turn_leds_off()

    # Movement methods
    async def drive_with_heading(self, speed: int, heading: int, reverse: bool = False) -> dict:
        """Drive at speed toward heading."""
        if not self._movement_service:
            return {"success": False, "error": "Not connected"}
        return await self._movement_service.drive_with_heading(speed, heading, reverse)

    async def stop(self) -> dict:
        """Stop RVR."""
        if not self._movement_service:
            return {"success": False, "error": "Not connected"}
        return await self._movement_service.stop()

    async def emergency_stop(self) -> dict:
        """Emergency stop."""
        if not self._movement_service:
            return {"success": False, "error": "Not connected"}
        return await self._movement_service.emergency_stop()

    # Sensor methods
    async def enable_color_detection(self, enabled: bool = True) -> dict:
        """Enable or disable the belly LED for color detection."""
        if not self._sensor_service:
            return {"success": False, "error": "Not connected"}
        return await self._sensor_service.enable_color_detection(enabled)

    async def get_color_detection(self, stabilization_ms: int = 50) -> dict:
        """Get color detection reading."""
        if not self._sensor_service:
            return {"success": False, "error": "Not connected"}
        return await self._sensor_service.get_color_detection(stabilization_ms)

    async def get_ambient_light(self) -> dict:
        """Get ambient light reading."""
        if not self._sensor_service:
            return {"success": False, "error": "Not connected"}
        return await self._sensor_service.get_ambient_light()

    # Safety methods
    async def set_speed_limit(self, max_speed_percent: float) -> dict:
        """Set speed limit."""
        if not self._safety_service:
            return {"success": False, "error": "Not connected"}
        return await self._safety_service.set_speed_limit(max_speed_percent)

    async def get_safety_status(self) -> dict:
        """Get safety status."""
        if not self._safety_service:
            return {"success": False, "error": "Not connected"}
        return await self._safety_service.get_safety_status()


# Convenience function for quick scripts
async def quick_connect(log_level: str = "WARNING") -> RVRClient:
    """Quick connect helper for scripts.

    Args:
        log_level: Logging level

    Returns:
        Connected RVR client

    Usage:
        client = await quick_connect()
        await client.set_all_leds(255, 165, 0)
        await client.shutdown()
    """
    client = RVRClient(log_level=log_level, log_format="console")
    await client.initialize()
    await client.connect()
    return client
