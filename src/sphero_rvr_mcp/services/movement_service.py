"""Movement service with command queue integration."""

import time

from ..core.command_queue import CommandQueue, CommandPriority
from ..hardware.connection_manager import ConnectionManager
from ..hardware.safety_monitor import SafetyMonitor
from ..observability.logging import get_logger, log_command_submitted, log_command_completed
from ..observability import metrics

logger = get_logger(__name__)


class MovementService:
    """Movement commands through command queue.

    All movement commands go through priority queue with safety checks.
    """

    def __init__(
        self,
        connection_manager: ConnectionManager,
        command_queue: CommandQueue,
        safety_monitor: SafetyMonitor,
    ):
        """Initialize movement service.

        Args:
            connection_manager: Connection manager
            command_queue: Command queue for serialization
            safety_monitor: Safety monitor for limits and checks
        """
        self._connection_manager = connection_manager
        self._command_queue = command_queue
        self._safety_monitor = safety_monitor

    async def drive_with_heading(
        self, speed: int, heading: int, reverse: bool = False
    ) -> dict:
        """Drive at speed toward heading.

        Args:
            speed: Speed 0-255
            heading: Heading 0-359 degrees
            reverse: Drive in reverse

        Returns:
            Drive result
        """
        start_time = time.time()
        log_command_submitted(logger, "drive_with_heading", speed=speed, heading=heading)

        try:
            # Ensure connected
            await self._connection_manager.ensure_connected()

            # Check emergency stop
            await self._safety_monitor.check_emergency_stop()

            # Apply speed limiting
            limited_speed, was_limited = await self._safety_monitor.limit_speed(speed)

            # Submit to command queue
            async def drive_command():
                flags = 1 if reverse else 0
                await self._connection_manager.rvr.drive_with_heading(
                    speed=limited_speed, heading=heading % 360, flags=flags
                )

            await self._command_queue.submit(
                drive_command, priority=CommandPriority.NORMAL, timeout=1.0
            )

            # Record command for timeout
            await self._safety_monitor.on_movement_command()

            duration = time.time() - start_time
            metrics.record_command_execution("drive_with_heading", duration, success=True)
            log_command_completed(logger, "drive_with_heading", duration * 1000)

            return {
                "success": True,
                "speed": limited_speed,
                "heading": heading % 360,
                "was_limited": was_limited,
            }

        except Exception as e:
            duration = time.time() - start_time
            metrics.record_command_execution("drive_with_heading", duration, success=False)
            logger.error("drive_with_heading_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def drive_tank(self, left_velocity: float, right_velocity: float) -> dict:
        """Drive with tank controls.

        Args:
            left_velocity: Left velocity -1.5 to 1.5 m/s
            right_velocity: Right velocity -1.5 to 1.5 m/s

        Returns:
            Drive result
        """
        start_time = time.time()
        log_command_submitted(logger, "drive_tank", left=left_velocity, right=right_velocity)

        try:
            await self._connection_manager.ensure_connected()
            await self._safety_monitor.check_emergency_stop()

            # Apply velocity limiting
            left_limited, left_was_limited = await self._safety_monitor.limit_velocity(left_velocity)
            right_limited, right_was_limited = await self._safety_monitor.limit_velocity(right_velocity)

            async def tank_command():
                await self._connection_manager.rvr.drive_tank_si_units(
                    left_velocity=left_limited, right_velocity=right_limited
                )

            await self._command_queue.submit(
                tank_command, priority=CommandPriority.NORMAL, timeout=1.0
            )

            await self._safety_monitor.on_movement_command()

            duration = time.time() - start_time
            metrics.record_command_execution("drive_tank", duration, success=True)

            return {
                "success": True,
                "left_velocity": left_limited,
                "right_velocity": right_limited,
                "was_limited": left_was_limited or right_was_limited,
            }

        except Exception as e:
            duration = time.time() - start_time
            metrics.record_command_execution("drive_tank", duration, success=False)
            return {"success": False, "error": str(e)}

    async def drive_rc(self, linear_velocity: float, yaw_velocity: float) -> dict:
        """Drive with RC controls.

        Args:
            linear_velocity: Forward velocity m/s
            yaw_velocity: Yaw rate deg/s

        Returns:
            Drive result
        """
        start_time = time.time()

        try:
            await self._connection_manager.ensure_connected()
            await self._safety_monitor.check_emergency_stop()

            linear_limited, was_limited = await self._safety_monitor.limit_velocity(linear_velocity)

            async def rc_command():
                await self._connection_manager.rvr.drive_rc_si_units(
                    linear_velocity=linear_limited, yaw_angular_velocity=yaw_velocity
                )

            await self._command_queue.submit(
                rc_command, priority=CommandPriority.NORMAL, timeout=1.0
            )

            await self._safety_monitor.on_movement_command()

            duration = time.time() - start_time
            metrics.record_command_execution("drive_rc", duration, success=True)

            return {"success": True, "linear_velocity": linear_limited, "was_limited": was_limited}

        except Exception as e:
            duration = time.time() - start_time
            metrics.record_command_execution("drive_rc", duration, success=False)
            return {"success": False, "error": str(e)}

    async def stop(self, deceleration: float = None) -> dict:
        """Stop RVR.

        Args:
            deceleration: Optional deceleration rate

        Returns:
            Stop result
        """
        try:
            await self._connection_manager.ensure_connected()

            async def stop_command():
                await self._connection_manager.rvr.drive_stop()

            await self._command_queue.submit(
                stop_command, priority=CommandPriority.HIGH, timeout=1.0
            )

            return {"success": True, "message": "Stopped"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def emergency_stop(self) -> dict:
        """Execute emergency stop.

        Returns:
            Emergency stop result
        """
        # Emergency stop bypasses command queue for immediate action
        return await self._safety_monitor.emergency_stop()

    async def clear_emergency_stop(self) -> dict:
        """Clear emergency stop.

        Returns:
            Result
        """
        return await self._safety_monitor.clear_emergency_stop()

    async def reset_yaw(self) -> dict:
        """Reset yaw to 0.

        Returns:
            Result
        """
        try:
            await self._connection_manager.ensure_connected()

            async def reset_command():
                await self._connection_manager.rvr.reset_yaw()

            await self._command_queue.submit(
                reset_command, priority=CommandPriority.LOW, timeout=1.0
            )

            return {"success": True, "message": "Yaw reset"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def reset_locator(self) -> dict:
        """Reset locator to origin.

        Returns:
            Result
        """
        try:
            await self._connection_manager.ensure_connected()

            async def reset_command():
                await self._connection_manager.rvr.reset_locator_x_and_y()

            await self._command_queue.submit(
                reset_command, priority=CommandPriority.LOW, timeout=1.0
            )

            return {"success": True, "message": "Locator reset"}

        except Exception as e:
            return {"success": False, "error": str(e)}
