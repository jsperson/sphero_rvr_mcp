"""Sensor service."""

from typing import List, Optional

from ..hardware.connection_manager import ConnectionManager
from ..hardware.sensor_stream_manager import SensorStreamManager
from ..observability.logging import get_logger

logger = get_logger(__name__)


class SensorService:
    """Sensor operations."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        sensor_manager: SensorStreamManager,
    ):
        """Initialize sensor service.

        Args:
            connection_manager: Connection manager
            sensor_manager: Sensor stream manager
        """
        self._connection_manager = connection_manager
        self._sensor_manager = sensor_manager

    async def start_sensor_streaming(self, sensors: List[str], interval_ms: int = 250) -> dict:
        """Start sensor streaming."""
        await self._connection_manager.ensure_connected()
        return await self._sensor_manager.start_streaming(sensors, interval_ms)

    async def stop_sensor_streaming(self) -> dict:
        """Stop sensor streaming."""
        await self._connection_manager.ensure_connected()
        return await self._sensor_manager.stop_streaming()

    async def get_sensor_data(self, sensors: Optional[List[str]] = None) -> dict:
        """Get cached sensor data."""
        await self._connection_manager.ensure_connected()
        return await self._sensor_manager.get_sensor_data(sensors)

    async def get_ambient_light(self) -> dict:
        """Get ambient light reading."""
        await self._connection_manager.ensure_connected()
        return await self._sensor_manager.query_ambient_light()

    async def enable_color_detection(self, enabled: bool = True) -> dict:
        """Enable/disable color detection LED."""
        await self._connection_manager.ensure_connected()
        
        try:
            await self._connection_manager.rvr.enable_color_detection(is_enabled=enabled)
            return {"success": True, "enabled": enabled}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_color_detection(self, stabilization_ms: int = 50) -> dict:
        """Get color detection reading."""
        await self._connection_manager.ensure_connected()
        return await self._sensor_manager.query_color_detection(stabilization_ms)

    async def get_battery_status(self) -> dict:
        """Get battery status."""
        await self._connection_manager.ensure_connected()

        percentage = await self._sensor_manager.query_battery_percentage()

        # Also get voltage state
        try:
            import asyncio
            voltage_response = await asyncio.wait_for(
                self._connection_manager.rvr.get_battery_voltage_state(),
                timeout=2.0
            )
            voltage_state = voltage_response.get('state', 'unknown')
        except Exception:
            voltage_state = 'unknown'

        return {
            "success": True,
            "percentage": percentage,
            "voltage_state": voltage_state,
        }
