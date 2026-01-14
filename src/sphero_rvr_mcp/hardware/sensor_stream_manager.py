"""Efficient sensor streaming with event bus integration.

This module replaces sensor_manager.py with optimized sensor handling that:
- Uses pre-built service map (no dir() loop)
- Integrates with event bus for distribution
- Provides thread-safe caching
- Includes comprehensive metrics
"""

import asyncio
import time
from typing import Optional, List, Dict, Any

from sphero_sdk import SpheroRvrAsync, RvrStreamingServices

from ..core.event_bus import EventBus, create_sensor_event
from ..core.state_manager import StateManager
from ..core.exceptions import SensorError
from ..observability.logging import get_logger, log_sensor_event
from ..observability import metrics

logger = get_logger(__name__)

# Pre-built sensor service map (O(1) lookup, no dir() loop)
# Only includes sensors actually available in RvrStreamingServices
SENSOR_SERVICE_MAP = {
    'accelerometer': RvrStreamingServices.accelerometer,
    'gyroscope': RvrStreamingServices.gyroscope,
    'imu': RvrStreamingServices.imu,
    'locator': RvrStreamingServices.locator,
    'velocity': RvrStreamingServices.velocity,
    'speed': RvrStreamingServices.speed,
    'quaternion': RvrStreamingServices.quaternion,
    'color_detection': RvrStreamingServices.color_detection,
    'ambient_light': RvrStreamingServices.ambient_light,
    'core_time': RvrStreamingServices.core_time,
}


class SensorStreamManager:
    """Efficient sensor streaming with event bus integration.

    Features:
    - Pre-built service map (no runtime introspection)
    - Event bus integration for decoupled distribution
    - Thread-safe caching with TTL
    - Comprehensive metrics and logging
    """

    def __init__(
        self,
        rvr: SpheroRvrAsync,
        state_manager: StateManager,
        event_bus: EventBus,
    ):
        """Initialize sensor stream manager.

        Args:
            rvr: RVR SDK instance
            state_manager: State management
            event_bus: Event bus for sensor data distribution
        """
        self._rvr = rvr
        self._state_manager = state_manager
        self._event_bus = event_bus
        self._registered_handlers: Dict[str, Any] = {}

    async def start_streaming(self, sensors: List[str], interval_ms: int = 250) -> dict:
        """Start streaming sensors and publish to event bus.

        Args:
            sensors: List of sensor names to stream
            interval_ms: Streaming interval (min 50ms)

        Returns:
            Result with list of successfully started sensors

        Raises:
            SensorError: Streaming setup failed
        """
        if interval_ms < 50:
            raise SensorError("Streaming interval must be >= 50ms")

        started_sensors = []
        failed_sensors = []

        for sensor in sensors:
            service = SENSOR_SERVICE_MAP.get(sensor.lower())

            if service is None:
                logger.warning("unknown_sensor", sensor=sensor)
                failed_sensors.append(sensor)
                continue

            try:
                # Create handler that publishes to event bus
                handler = self._create_handler(sensor)

                # Register with RVR SDK
                await self._rvr.sensor_control.add_sensor_data_handler(
                    service=service,
                    handler=handler,
                )

                self._registered_handlers[sensor] = handler
                started_sensors.append(sensor)

                log_sensor_event(logger, sensor, "streaming_started")
                metrics.sensor_events_total.labels(sensor=sensor).inc()

            except Exception as e:
                logger.error("sensor_streaming_failed", sensor=sensor, error=str(e))
                failed_sensors.append(sensor)

        # Update state
        if started_sensors:
            await self._state_manager.sensor_state.set_streaming(
                active=True,
                sensors=started_sensors,
                interval_ms=interval_ms,
            )

            # Start streaming
            try:
                await self._rvr.sensor_control.start(interval=interval_ms)
                metrics.sensor_streaming_active.set(1)
                logger.info("sensor_streaming_started", sensors=started_sensors, interval_ms=interval_ms)
            except Exception as e:
                logger.error("sensor_streaming_start_failed", error=str(e))
                raise SensorError(f"Failed to start streaming: {str(e)}")

        return {
            "success": len(started_sensors) > 0,
            "started_sensors": started_sensors,
            "failed_sensors": failed_sensors,
            "interval_ms": interval_ms,
        }

    async def stop_streaming(self) -> dict:
        """Stop all sensor streaming.

        Returns:
            Result of stop operation
        """
        try:
            # Stop streaming
            await self._rvr.sensor_control.stop()

            # Clear handlers
            for sensor, handler in self._registered_handlers.items():
                try:
                    await self._rvr.sensor_control.remove_sensor_data_handler(handler)
                except Exception as e:
                    logger.warning("handler_removal_failed", sensor=sensor, error=str(e))

            self._registered_handlers.clear()

            # Clear state and cache
            await self._state_manager.sensor_state.set_streaming(active=False, sensors=[], interval_ms=250)
            await self._state_manager.sensor_state.clear_cache()

            metrics.sensor_streaming_active.set(0)
            log_sensor_event(logger, "all", "streaming_stopped")

            return {"success": True, "message": "Streaming stopped"}

        except Exception as e:
            logger.error("sensor_streaming_stop_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_sensor_data(self, sensors: Optional[List[str]] = None) -> dict:
        """Get cached sensor data.

        Args:
            sensors: Specific sensors to get (None = all streaming sensors)

        Returns:
            Sensor data with freshness info
        """
        if sensors is None:
            state_snapshot = await self._state_manager.sensor_state.snapshot()
            sensors = state_snapshot.get("streaming_sensors", [])

        results = {}

        for sensor in sensors:
            cached = await self._state_manager.sensor_state.get_cached_data(sensor)

            if cached is None:
                results[sensor] = {
                    "available": False,
                    "reason": "no_data_or_stale",
                }
            else:
                results[sensor] = {
                    "available": True,
                    "data": cached["data"],
                    "age_ms": cached["age_ms"],
                }

                # Record metrics
                metrics.record_sensor_event(sensor, age_ms=cached["age_ms"])

        return {"success": True, "sensors": results}

    async def query_ambient_light(self, timeout: float = 2.0) -> dict:
        """Query ambient light sensor directly.

        Args:
            timeout: Query timeout

        Returns:
            Ambient light value

        Raises:
            SensorError: Query failed or timed out
        """
        try:
            result = await asyncio.wait_for(
                self._rvr.get_ambient_light_sensor_value(),
                timeout=timeout,
            )

            return {
                "success": True,
                "light_value": result.get("ambientLightValue", 0),
            }

        except asyncio.TimeoutError:
            raise SensorError(f"Ambient light query timed out after {timeout}s")
        except Exception as e:
            raise SensorError(f"Ambient light query failed: {str(e)}")

    async def query_color_detection(self, stabilization_ms: int = 50, timeout: float = 2.0) -> dict:
        """Query color sensor directly with configurable stabilization.

        This replaces the hard-coded 100ms sleep with a configurable delay (default 50ms).

        Args:
            stabilization_ms: Stabilization delay (default 50ms, not 100ms)
            timeout: Query timeout

        Returns:
            Color values (R, G, B, C)

        Raises:
            SensorError: Query failed or timed out
        """
        try:
            # Enable color detection LED
            await self._rvr.enable_color_detection(is_enabled=True)

            # Configurable stabilization delay
            await asyncio.sleep(stabilization_ms / 1000.0)

            # Query with timeout
            result = await asyncio.wait_for(
                self._rvr.get_rgbc_sensor_values(),
                timeout=timeout,
            )

            # Disable LED
            await self._rvr.enable_color_detection(is_enabled=False)

            return {
                "success": True,
                "r": result.get("redChannelValue", 0),
                "g": result.get("greenChannelValue", 0),
                "b": result.get("blueChannelValue", 0),
                "c": result.get("clearChannelValue", 0),
            }

        except asyncio.TimeoutError:
            raise SensorError(f"Color detection query timed out after {timeout}s")
        except Exception as e:
            raise SensorError(f"Color detection query failed: {str(e)}")
        finally:
            # Ensure LED is disabled even on error
            try:
                await self._rvr.enable_color_detection(is_enabled=False)
            except Exception:
                pass

    async def query_battery_percentage(self, timeout: float = 2.0) -> Optional[float]:
        """Query battery percentage.

        Args:
            timeout: Query timeout

        Returns:
            Battery percentage (0-100) or None if unavailable
        """
        try:
            result = await asyncio.wait_for(
                self._rvr.get_battery_percentage(),
                timeout=timeout,
            )
            percentage = result.get("percentage", 0)
            metrics.update_battery_metrics(percentage, None)
            return percentage

        except asyncio.TimeoutError:
            logger.warning("battery_percentage_query_timeout")
            return None
        except Exception as e:
            logger.warning("battery_percentage_query_failed", error=str(e))
            return None

    def _create_handler(self, sensor: str):
        """Create sensor data handler that publishes to event bus.

        Args:
            sensor: Sensor name

        Returns:
            Handler function
        """
        async def handler(data):
            """Handle sensor data."""
            try:
                # Update cache
                await self._state_manager.sensor_state.update_cache(sensor, data)

                # Publish to event bus
                event = create_sensor_event(sensor, data)
                await self._event_bus.publish(event)

                metrics.sensor_events_total.labels(sensor=sensor).inc()

            except Exception as e:
                logger.error("sensor_handler_failed", sensor=sensor, error=str(e))

        return handler
