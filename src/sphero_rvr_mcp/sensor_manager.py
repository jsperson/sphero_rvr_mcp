"""Sensor streaming and data management."""

import asyncio
import time
from typing import Optional, Callable, Any

from .config import SensorConfig
from .rvr_manager import RvrManager


# Mapping of sensor names to SDK streaming service names
SENSOR_SERVICES = {
    'accelerometer': 'Accelerometer',
    'gyroscope': 'Gyroscope',
    'imu': 'IMU',
    'locator': 'Locator',
    'velocity': 'Velocity',
    'speed': 'Speed',
    'quaternion': 'Quaternion',
    'color_detection': 'ColorDetection',
    'ambient_light': 'AmbientLight',
    'encoders': 'Encoders',
    'core_time': 'CoreTime',
}


class SensorManager:
    """Manages sensor streaming and data access.

    Provides both streaming (background) and on-demand sensor queries.
    Caches streaming data for quick access.
    """

    def __init__(self, rvr_manager: RvrManager, config: SensorConfig):
        """Initialize sensor manager.

        Args:
            rvr_manager: RVR connection manager.
            config: Sensor configuration.
        """
        self._rvr_manager = rvr_manager
        self._config = config
        self._streaming_enabled = False
        self._streaming_interval_ms = config.default_streaming_interval_ms
        self._enabled_sensors: set[str] = set()

        # Thread-safe sensor data storage
        self._sensor_data: dict[str, dict] = {}
        self._last_update_times: dict[str, float] = {}
        self._data_lock = asyncio.Lock()

    @property
    def is_streaming(self) -> bool:
        """Check if sensor streaming is active."""
        return self._streaming_enabled

    @property
    def enabled_sensors(self) -> list[str]:
        """Get list of currently enabled sensors."""
        return list(self._enabled_sensors)

    def _get_service_name(self, sensor: str) -> Optional[str]:
        """Convert sensor name to SDK service name.

        Args:
            sensor: Sensor name (lowercase).

        Returns:
            SDK service name or None if not found.
        """
        return SENSOR_SERVICES.get(sensor.lower())

    async def _create_sensor_handler(self, sensor_name: str) -> Callable:
        """Create a handler function for a specific sensor.

        Args:
            sensor_name: Name of the sensor.

        Returns:
            Async handler function that stores sensor data.
        """
        async def handler(data: dict):
            async with self._data_lock:
                self._sensor_data[sensor_name] = data
                self._last_update_times[sensor_name] = time.time()

        return handler

    async def start_streaming(
        self,
        sensors: list[str],
        interval_ms: Optional[int] = None
    ) -> list[str]:
        """Start streaming for specified sensors.

        Args:
            sensors: List of sensor names to stream.
            interval_ms: Streaming interval in milliseconds.

        Returns:
            List of successfully enabled sensors.

        Raises:
            ConnectionError: If RVR not connected.
        """
        self._rvr_manager.ensure_connected()
        rvr = self._rvr_manager.rvr

        # Import SDK types
        from sphero_sdk import RvrStreamingServices

        # Validate and map sensors
        enabled = []
        for sensor in sensors:
            service_name = self._get_service_name(sensor)
            if service_name is None:
                continue

            # Get the service attribute from RvrStreamingServices
            if not hasattr(RvrStreamingServices, sensor.lower()):
                # Try exact service name
                service_attr = None
                for attr in dir(RvrStreamingServices):
                    if getattr(RvrStreamingServices, attr) == service_name:
                        service_attr = getattr(RvrStreamingServices, attr)
                        break
                if service_attr is None:
                    continue
            else:
                service_attr = getattr(RvrStreamingServices, sensor.lower())

            # Create and register handler
            handler = await self._create_sensor_handler(sensor.lower())
            await rvr.sensor_control.add_sensor_data_handler(
                service=service_attr,
                handler=handler
            )
            enabled.append(sensor.lower())
            self._enabled_sensors.add(sensor.lower())

        if enabled:
            # Set interval and start streaming
            interval = interval_ms or self._config.default_streaming_interval_ms
            interval = max(interval, self._config.min_streaming_interval_ms)
            self._streaming_interval_ms = interval

            await rvr.sensor_control.start(interval=interval)
            self._streaming_enabled = True

        return enabled

    async def stop_streaming(self) -> bool:
        """Stop all sensor streaming.

        Returns:
            True if stopped successfully.
        """
        if not self._streaming_enabled:
            return True

        try:
            self._rvr_manager.ensure_connected()
            rvr = self._rvr_manager.rvr

            await rvr.sensor_control.stop()
            await rvr.sensor_control.clear()

            self._streaming_enabled = False
            self._enabled_sensors.clear()

            async with self._data_lock:
                self._sensor_data.clear()
                self._last_update_times.clear()

            return True

        except Exception:
            return False

    async def get_streaming_data(
        self,
        sensors: Optional[list[str]] = None
    ) -> dict[str, dict]:
        """Get current sensor data from streaming cache.

        Args:
            sensors: Specific sensors to get, or None for all.

        Returns:
            Dict of sensor name to data with age info.
        """
        async with self._data_lock:
            result = {}
            current_time = time.time()

            sensors_to_get = sensors or list(self._sensor_data.keys())

            for sensor in sensors_to_get:
                sensor_lower = sensor.lower()
                if sensor_lower in self._sensor_data:
                    update_time = self._last_update_times.get(sensor_lower, 0)
                    age_ms = (current_time - update_time) * 1000

                    # Check if data is stale
                    ttl_ms = self._config.sensor_data_ttl_seconds * 1000
                    is_fresh = age_ms < ttl_ms

                    result[sensor_lower] = {
                        'data': self._sensor_data[sensor_lower],
                        'age_ms': age_ms,
                        'is_fresh': is_fresh
                    }

            return result

    async def get_accelerometer(self) -> Optional[dict]:
        """Get accelerometer data from streaming cache."""
        data = await self.get_streaming_data(['accelerometer'])
        if 'accelerometer' in data:
            return data['accelerometer']['data']
        return None

    # Direct sensor queries (on-demand, not from streaming cache)

    async def query_ambient_light(self) -> Optional[float]:
        """Query ambient light sensor directly.

        Returns:
            Ambient light value or None on error.
        """
        self._rvr_manager.ensure_connected()
        rvr = self._rvr_manager.rvr

        try:
            response = await rvr.get_ambient_light_sensor_value()
            if response:
                return response.get('ambient_light_value')
        except Exception:
            pass
        return None

    async def query_color_detection(self) -> Optional[dict]:
        """Query color sensor directly.

        Returns:
            Color data dict or None on error.
        """
        self._rvr_manager.ensure_connected()
        rvr = self._rvr_manager.rvr

        try:
            response = await rvr.get_rgbc_sensor_values()
            if response:
                return {
                    'r': response.get('red_channel_value', 0),
                    'g': response.get('green_channel_value', 0),
                    'b': response.get('blue_channel_value', 0),
                    'c': response.get('clear_channel_value', 0)
                }
        except Exception:
            pass
        return None

    async def query_battery_percentage(self) -> Optional[int]:
        """Query battery percentage directly.

        Returns:
            Battery percentage 0-100 or None on error.
        """
        self._rvr_manager.ensure_connected()
        rvr = self._rvr_manager.rvr

        try:
            response = await rvr.get_battery_percentage()
            if response:
                return response.get('percentage')
        except Exception:
            pass
        return None

    async def query_battery_voltage(self) -> Optional[dict]:
        """Query battery voltage state.

        Returns:
            Dict with voltage info or None on error.
        """
        self._rvr_manager.ensure_connected()
        rvr = self._rvr_manager.rvr

        try:
            response = await rvr.get_battery_voltage_state()
            if response:
                return {
                    'state': response.get('state', 'unknown'),
                    'voltage': response.get('voltage', 0.0)
                }
        except Exception:
            pass
        return None

    async def query_motor_temperatures(self) -> Optional[dict]:
        """Query motor thermal status.

        Returns:
            Dict with motor temperatures or None on error.
        """
        self._rvr_manager.ensure_connected()
        rvr = self._rvr_manager.rvr

        try:
            # This may require enabling thermal notifications first
            # For now, return placeholder - actual implementation depends on SDK
            return {
                'left_temp': 0.0,
                'right_temp': 0.0,
                'left_status': 'ok',
                'right_status': 'ok'
            }
        except Exception:
            pass
        return None
