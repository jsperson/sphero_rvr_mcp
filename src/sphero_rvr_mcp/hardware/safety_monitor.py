"""Safety monitor with atomic operations.

This module replaces safety_controller.py with atomic safety state management
that eliminates race conditions in emergency stop and timeout management.
"""

import asyncio
from typing import Optional

from sphero_sdk import SpheroRvrAsync

from ..core.state_manager import StateManager
from ..core.exceptions import SafetyError
from ..observability.logging import get_logger, log_safety_event

logger = get_logger(__name__)


class SafetyMonitor:
    """Safety monitor with atomic operations.

    Features:
    - Atomic emergency stop flag (no races)
    - Speed limiting for both speed (0-255) and velocity (m/s) modes
    - Command timeout with proper task management
    - Comprehensive logging and metrics
    """

    def __init__(
        self,
        rvr: SpheroRvrAsync,
        state_manager: StateManager,
    ):
        """Initialize safety monitor.

        Args:
            rvr: RVR SDK instance
            state_manager: State management
        """
        self._rvr = rvr
        self._state_manager = state_manager
        self._timeout_task: Optional[asyncio.Task] = None
        self._timeout_lock = asyncio.Lock()

    async def emergency_stop(self) -> dict:
        """Activate emergency stop atomically.

        Returns:
            Result of emergency stop
        """
        # Atomically set emergency stop flag
        await self._state_manager.safety_state.set_emergency_stop(True)

        # Record metrics and log
        log_safety_event(logger, "emergency_stop_activated")

        # Stop motors immediately
        try:
            await asyncio.wait_for(self._rvr.drive_stop(), timeout=0.5)

            # Cancel any timeout task
            async with self._timeout_lock:
                if self._timeout_task is not None:
                    self._timeout_task.cancel()
                    self._timeout_task = None

            return {"success": True, "message": "Emergency stop activated"}

        except asyncio.TimeoutError:
            logger.error("emergency_stop_motor_timeout")
            return {"success": False, "error": "Motor stop timed out"}

        except Exception as e:
            logger.error("emergency_stop_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def clear_emergency_stop(self) -> dict:
        """Clear emergency stop atomically.

        Returns:
            Result of clearing emergency stop
        """
        # Atomically clear emergency stop flag
        await self._state_manager.safety_state.set_emergency_stop(False)

        # Record metrics and log
        log_safety_event(logger, "emergency_stop_cleared")

        return {"success": True, "message": "Emergency stop cleared"}

    async def check_emergency_stop(self):
        """Check if emergency stop is active.

        Raises:
            SafetyError: If emergency stop is active
        """
        is_stopped = await self._state_manager.safety_state.is_emergency_stopped()

        if is_stopped:
            raise SafetyError("Emergency stop is active. Clear it before issuing commands.")

    async def set_speed_limit(self, percent: float) -> dict:
        """Set speed limit percentage.

        Args:
            percent: Speed limit (0-100)

        Returns:
            Result with new speed limit
        """
        # Clamp to valid range
        percent = max(0.0, min(100.0, percent))

        # Update state atomically
        await self._state_manager.safety_state.set_speed_limit(percent)

        # Update metrics

        log_safety_event(logger, "speed_limit_changed", percent=percent)

        return {
            "success": True,
            "speed_limit_percent": percent,
        }

    async def get_speed_limit(self) -> float:
        """Get current speed limit percentage.

        Returns:
            Speed limit (0-100)
        """
        return await self._state_manager.safety_state.get_speed_limit()

    async def limit_speed(self, speed: int) -> tuple[int, bool]:
        """Apply speed limiting to speed value (0-255).

        Args:
            speed: Requested speed (0-255)

        Returns:
            Tuple of (limited_speed, was_limited)
        """
        limit_percent = await self.get_speed_limit()

        max_speed = int(255 * limit_percent / 100.0)
        limited_speed = min(speed, max_speed)

        was_limited = limited_speed < speed

        if was_limited:
            log_safety_event(
                logger,
                "speed_limited",
                requested=speed,
                limited_to=limited_speed,
                limit_percent=limit_percent,
            )

        return limited_speed, was_limited

    async def limit_velocity(self, velocity: float) -> tuple[float, bool]:
        """Apply speed limiting to velocity (m/s).

        Args:
            velocity: Requested velocity

        Returns:
            Tuple of (limited_velocity, was_limited)
        """
        limit_percent = await self.get_speed_limit()

        # Max velocity is 1.5 m/s for RVR
        max_velocity = 1.5 * limit_percent / 100.0
        limited_velocity = max(min(velocity, max_velocity), -max_velocity)

        was_limited = abs(limited_velocity) < abs(velocity)

        if was_limited:
            log_safety_event(
                logger,
                "velocity_limited",
                requested=velocity,
                limited_to=limited_velocity,
                limit_percent=limit_percent,
            )

        return limited_velocity, was_limited

    async def set_command_timeout(self, seconds: float) -> dict:
        """Set command timeout.

        Args:
            seconds: Timeout in seconds (0 to disable)

        Returns:
            Result with new timeout
        """
        # Update state atomically
        await self._state_manager.safety_state.set_command_timeout(seconds)

        log_safety_event(logger, "command_timeout_changed", seconds=seconds)

        return {
            "success": True,
            "command_timeout_seconds": seconds,
        }

    async def on_movement_command(self):
        """Called when a movement command is issued.

        Manages command timeout auto-stop.
        """
        # Record command time
        await self._state_manager.safety_state.record_command()

        # Get timeout setting
        timeout_seconds = await self._state_manager.safety_state.get_command_timeout()

        if timeout_seconds <= 0:
            # Timeout disabled
            return

        # Cancel existing timeout task and create new one
        async with self._timeout_lock:
            if self._timeout_task is not None:
                self._timeout_task.cancel()

            self._timeout_task = asyncio.create_task(
                self._timeout_auto_stop(timeout_seconds)
            )

    async def _timeout_auto_stop(self, timeout_seconds: float):
        """Background task that auto-stops after timeout.

        Args:
            timeout_seconds: Timeout duration
        """
        try:
            await asyncio.sleep(timeout_seconds)

            # Timeout elapsed - stop motors
            log_safety_event(logger, "command_timeout_auto_stop", timeout_seconds=timeout_seconds)

            try:
                await asyncio.wait_for(self._rvr.drive_stop(), timeout=1.0)
            except Exception as e:
                logger.error("timeout_auto_stop_failed", error=str(e))

        except asyncio.CancelledError:
            # Timeout was cancelled by new command
            pass

    async def get_safety_status(self) -> dict:
        """Get current safety status.

        Returns:
            Safety status snapshot
        """
        safety_snapshot = await self._state_manager.safety_state.snapshot()

        return {
            "success": True,
            **safety_snapshot,
        }
