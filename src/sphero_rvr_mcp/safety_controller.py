"""Safety system for RVR control."""

import asyncio
import time
from typing import Optional, Tuple

from .config import SafetyConfig
from .rvr_manager import RvrManager
from .sensor_manager import SensorManager


# RVR physical limits
MAX_SPEED_VALUE = 255  # Maximum speed value for drive commands
MAX_VELOCITY_MS = 1.5  # Maximum velocity in m/s


class SafetyController:
    """Safety system for RVR movement control.

    Provides:
    - Speed limiting (configurable percentage)
    - Command timeout (auto-stop if no commands received)
    - Emergency stop
    - Basic collision detection via accelerometer
    """

    def __init__(
        self,
        config: SafetyConfig,
        rvr_manager: RvrManager,
        sensor_manager: Optional[SensorManager] = None
    ):
        """Initialize safety controller.

        Args:
            config: Safety configuration.
            rvr_manager: RVR connection manager.
            sensor_manager: Sensor manager for collision detection (optional).
        """
        self._config = config
        self._rvr_manager = rvr_manager
        self._sensor_manager = sensor_manager

        # Speed limiting
        self._max_speed_percent = config.default_max_speed_percent

        # Command timeout
        self._timeout_seconds = config.command_timeout_seconds
        self._timeout_enabled = True
        self._last_command_time: Optional[float] = None
        self._timeout_task: Optional[asyncio.Task] = None

        # Emergency stop state
        self._emergency_stopped = False

    @property
    def speed_limit_percent(self) -> float:
        """Get current speed limit percentage."""
        return self._max_speed_percent

    @property
    def timeout_seconds(self) -> float:
        """Get current command timeout in seconds."""
        return self._timeout_seconds

    @property
    def timeout_enabled(self) -> bool:
        """Check if command timeout is enabled."""
        return self._timeout_enabled

    @property
    def is_emergency_stopped(self) -> bool:
        """Check if emergency stop is active."""
        return self._emergency_stopped

    @property
    def last_command_age_ms(self) -> Optional[float]:
        """Get age of last movement command in milliseconds."""
        if self._last_command_time is None:
            return None
        return (time.time() - self._last_command_time) * 1000

    def set_speed_limit(self, percent: float) -> float:
        """Set maximum speed limit.

        Args:
            percent: Speed limit 0-100.

        Returns:
            Actual speed limit set (clamped to valid range).
        """
        self._max_speed_percent = max(0.0, min(100.0, percent))
        return self._max_speed_percent

    def set_timeout(self, seconds: float) -> float:
        """Set command timeout.

        Args:
            seconds: Timeout in seconds. Set to 0 to disable.

        Returns:
            Actual timeout set.
        """
        if seconds <= 0:
            self._timeout_enabled = False
            self._timeout_seconds = 0
        else:
            self._timeout_enabled = True
            self._timeout_seconds = seconds
        return self._timeout_seconds

    def limit_speed(self, requested_speed: int) -> Tuple[int, bool]:
        """Apply speed limit to requested speed value.

        Args:
            requested_speed: Requested speed 0-255.

        Returns:
            Tuple of (limited_speed, was_limited).
        """
        max_allowed = int(MAX_SPEED_VALUE * (self._max_speed_percent / 100.0))
        abs_speed = abs(requested_speed)

        if abs_speed > max_allowed:
            # Preserve sign
            sign = 1 if requested_speed >= 0 else -1
            return max_allowed * sign, True

        return requested_speed, False

    def limit_velocity(self, velocity: float) -> Tuple[float, bool]:
        """Apply speed limit to velocity in m/s.

        Args:
            velocity: Requested velocity in m/s.

        Returns:
            Tuple of (limited_velocity, was_limited).
        """
        max_velocity = MAX_VELOCITY_MS * (self._max_speed_percent / 100.0)

        if abs(velocity) > max_velocity:
            sign = 1 if velocity >= 0 else -1
            return max_velocity * sign, True

        return velocity, False

    async def on_movement_command(self) -> None:
        """Called before each movement command.

        Updates timeout timer and checks emergency stop.

        Raises:
            RuntimeError: If emergency stop is active.
        """
        if self._emergency_stopped:
            raise RuntimeError(
                "Emergency stop is active. Call clear_emergency_stop() first."
            )

        self._last_command_time = time.time()

        # Cancel existing timeout task
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

        # Start new timeout task
        if self._timeout_enabled and self._timeout_seconds > 0:
            self._timeout_task = asyncio.create_task(self._timeout_check())

    async def _timeout_check(self) -> None:
        """Background task that triggers auto-stop when timeout expires."""
        try:
            await asyncio.sleep(self._timeout_seconds)
            await self._auto_stop()
        except asyncio.CancelledError:
            pass

    async def _auto_stop(self) -> None:
        """Stop motors due to command timeout."""
        if self._rvr_manager.is_connected:
            try:
                await self._rvr_manager.rvr.drive_stop()
            except Exception:
                pass

    async def emergency_stop(self) -> bool:
        """Execute emergency stop.

        Immediately stops motors and sets emergency stop flag.

        Returns:
            True if stop executed successfully.
        """
        self._emergency_stopped = True

        # Cancel timeout task
        if self._timeout_task is not None:
            self._timeout_task.cancel()

        if self._rvr_manager.is_connected:
            try:
                await self._rvr_manager.rvr.drive_stop()
                return True
            except Exception:
                return False

        return True

    def clear_emergency_stop(self) -> None:
        """Clear emergency stop flag to allow movement again."""
        self._emergency_stopped = False

    async def check_collision(self) -> bool:
        """Check for collision based on accelerometer data.

        Returns:
            True if collision detected.
        """
        if not self._config.enable_collision_detection:
            return False

        if self._sensor_manager is None:
            return False

        try:
            accel = await self._sensor_manager.get_accelerometer()
            if accel:
                x = accel.get('X', 0)
                y = accel.get('Y', 0)
                z = accel.get('Z', 0)

                # Calculate magnitude (subtract 1g for gravity)
                # This is a simplified check
                magnitude = (x**2 + y**2 + (z - 1)**2) ** 0.5

                if magnitude > self._config.collision_threshold_g:
                    return True
        except Exception:
            pass

        return False

    def get_status(self) -> dict:
        """Get current safety system status.

        Returns:
            Dict with safety status info.
        """
        return {
            'speed_limit_percent': self._max_speed_percent,
            'timeout_enabled': self._timeout_enabled,
            'timeout_seconds': self._timeout_seconds,
            'last_command_age_ms': self.last_command_age_ms,
            'emergency_stopped': self._emergency_stopped,
            'collision_detection_enabled': self._config.enable_collision_detection
        }
