"""Movement service with command queue integration."""

import asyncio
import time

from ..core.command_queue import CommandQueue
from ..hardware.connection_manager import ConnectionManager
from ..hardware.safety_monitor import SafetyMonitor
from ..observability.logging import get_logger, log_command_submitted, log_command_completed

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
                drive_command, timeout=1.0
            )

            # Record command for timeout
            await self._safety_monitor.on_movement_command()

            duration = time.time() - start_time
            log_command_completed(logger, "drive_with_heading", duration * 1000)

            return {
                "success": True,
                "speed": limited_speed,
                "heading": heading % 360,
                "was_limited": was_limited,
            }

        except Exception as e:
            duration = time.time() - start_time
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
                tank_command, timeout=1.0
            )

            await self._safety_monitor.on_movement_command()

            duration = time.time() - start_time

            return {
                "success": True,
                "left_velocity": left_limited,
                "right_velocity": right_limited,
                "was_limited": left_was_limited or right_was_limited,
            }

        except Exception as e:
            duration = time.time() - start_time
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
                rc_command, timeout=1.0
            )

            await self._safety_monitor.on_movement_command()

            duration = time.time() - start_time

            return {"success": True, "linear_velocity": linear_limited, "was_limited": was_limited}

        except Exception as e:
            duration = time.time() - start_time
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
                stop_command, timeout=1.0
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
                reset_command, timeout=1.0
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
                reset_command, timeout=1.0
            )

            return {"success": True, "message": "Locator reset"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def pivot(self, degrees: float, speed: int = 0) -> dict:
        """Pivot (turn in place) by a specified number of degrees.

        Uses reset_yaw + drive_with_heading pattern to rotate without
        forward motion.

        Args:
            degrees: Degrees to turn. Positive = turn right (clockwise),
                     negative = turn left (counter-clockwise).
            speed: Rotation speed 0-255 (0 = let RVR control rotation speed)

        Returns:
            Result with actual degrees turned
        """
        start_time = time.time()
        log_command_submitted(logger, "pivot", degrees=degrees)

        try:
            await self._connection_manager.ensure_connected()
            await self._safety_monitor.check_emergency_stop()

            # Calculate target heading (0-359)
            # Positive degrees = right = positive heading
            # Negative degrees = left = needs to wrap (e.g., -90 = 270)
            target_heading = int(degrees) % 360
            if target_heading < 0:
                target_heading += 360

            # Step 1: Reset yaw so current direction = heading 0
            async def reset_yaw_command():
                await self._connection_manager.rvr.reset_yaw()

            await self._command_queue.submit(
                reset_yaw_command, timeout=1.0
            )

            # Small delay for yaw reset to take effect
            await asyncio.sleep(0.1)

            # Step 2: Drive with heading to rotate (speed 0 = rotate only)
            async def rotate_command():
                await self._connection_manager.rvr.drive_with_heading(
                    speed=speed, heading=target_heading, flags=0
                )

            await self._command_queue.submit(
                rotate_command, timeout=1.0
            )

            # Wait for rotation to complete (firmware handles it, we use conservative estimate)
            # The RVR's firmware uses its internal magnetometer for closed-loop control
            rotation_time = abs(degrees) / 90.0 * 2.0  # Conservative: ~2s per 90 degrees
            rotation_time = max(0.5, min(rotation_time, 15.0))  # Clamp 0.5-15s
            await asyncio.sleep(rotation_time)

            # Step 3: Reset yaw again so new direction = heading 0
            await self._command_queue.submit(
                reset_yaw_command, timeout=1.0
            )

            # Step 4: Stop (now heading 0 = current direction, so no correction)
            async def stop_command():
                await self._connection_manager.rvr.drive_stop()

            await self._command_queue.submit(
                stop_command, timeout=1.0
            )

            duration = time.time() - start_time
            log_command_completed(logger, "pivot", duration * 1000)

            return {
                "success": True,
                "degrees": degrees,
                "target_heading": target_heading,
                "rotation_time": rotation_time,
            }

        except Exception as e:
            duration = time.time() - start_time
            logger.error("pivot_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def drive_forward(
        self,
        distance: float,
        speed: float = 0.5,
        tolerance: float = 0.01,
        timeout_seconds: float = 30.0
    ) -> dict:
        """Drive forward a specified distance in meters.

        Uses locator sensor for accurate distance measurement.
        Maintains current heading (does not reset yaw).

        Args:
            distance: Distance to travel in meters
            speed: Travel speed in m/s (default: 0.5, max: 1.5)
            tolerance: Acceptable distance error in meters (default: 0.01 = 1cm)
            timeout_seconds: Maximum time to complete (default: 30)

        Returns:
            Result with actual distance traveled
        """
        import math

        start_time = time.time()
        log_command_submitted(logger, "drive_forward", distance=distance, speed=speed)

        try:
            await self._connection_manager.ensure_connected()
            await self._safety_monitor.check_emergency_stop()

            # Validate and clamp speed
            speed = max(0.1, min(1.5, abs(speed)))

            # Apply safety speed limit
            speed_pct = (speed / 1.5) * 100  # Convert to percentage
            limited_speed_pct, was_limited = self._safety_monitor.limit_speed(speed_pct)
            actual_speed = (limited_speed_pct / 100.0) * 1.5

            # Reset locator to origin
            await self.reset_locator()
            await asyncio.sleep(0.1)

            # Ensure locator is streaming
            from ..hardware.sensor_stream_manager import SensorStreamManager
            sensor_manager = SensorStreamManager(
                rvr=self._connection_manager.rvr,
                state_manager=self._connection_manager._state_manager
            )
            await sensor_manager.ensure_locator_streaming(interval_ms=50)

            poll_interval = 0.05
            distance_traveled = 0.0

            while True:
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    await self.stop()
                    logger.warning("drive_forward_timeout", distance=distance, traveled=distance_traveled)
                    return {
                        "success": False,
                        "error": "Timeout reached",
                        "distance_traveled": distance_traveled,
                        "target_distance": distance,
                        "elapsed_seconds": elapsed
                    }

                # Check emergency stop
                await self._safety_monitor.check_emergency_stop()

                # Get current position from locator
                position = await sensor_manager.get_locator_position(timeout=0.5)

                if position is None:
                    # Keep driving while waiting for sensor data
                    async def drive_cmd():
                        await self._connection_manager.rvr.drive_rc_si_units(
                            linear_velocity=actual_speed,
                            yaw_angular_velocity=0
                        )

                    await self._command_queue.submit(drive_cmd, timeout=0.5)
                    await asyncio.sleep(poll_interval)
                    continue

                # Calculate distance traveled
                distance_traveled = math.sqrt(position['x']**2 + position['y']**2)

                # Check if target reached
                remaining = distance - distance_traveled
                if remaining <= tolerance:
                    await self.stop()
                    duration = time.time() - start_time
                    log_command_completed(logger, "drive_forward", duration * 1000)
                    return {
                        "success": True,
                        "distance_traveled": distance_traveled,
                        "target_distance": distance,
                        "elapsed_seconds": duration
                    }

                # Slow down near target
                current_speed = actual_speed
                if remaining < 0.05:  # Within 5cm
                    current_speed = max(0.1, actual_speed * (remaining / 0.05))

                # Drive forward
                async def drive_cmd():
                    await self._connection_manager.rvr.drive_rc_si_units(
                        linear_velocity=current_speed,
                        yaw_angular_velocity=0
                    )

                await self._command_queue.submit(drive_cmd, timeout=0.5)
                await asyncio.sleep(poll_interval)

        except Exception as e:
            await self.stop()
            duration = time.time() - start_time
            logger.error("drive_forward_failed", error=str(e))
            return {"success": False, "error": str(e)}

    async def drive_backward(
        self,
        distance: float,
        speed: float = 0.5,
        tolerance: float = 0.01,
        timeout_seconds: float = 30.0
    ) -> dict:
        """Drive backward a specified distance in meters.

        Uses locator sensor for accurate distance measurement.
        Maintains current heading (does not reset yaw).

        Args:
            distance: Distance to travel in meters
            speed: Travel speed in m/s (default: 0.5, max: 1.5)
            tolerance: Acceptable distance error in meters (default: 0.01 = 1cm)
            timeout_seconds: Maximum time to complete (default: 30)

        Returns:
            Result with actual distance traveled
        """
        import math

        start_time = time.time()
        log_command_submitted(logger, "drive_backward", distance=distance, speed=speed)

        try:
            await self._connection_manager.ensure_connected()
            await self._safety_monitor.check_emergency_stop()

            # Validate and clamp speed
            speed = max(0.1, min(1.5, abs(speed)))

            # Apply safety speed limit
            speed_pct = (speed / 1.5) * 100  # Convert to percentage
            limited_speed_pct, was_limited = self._safety_monitor.limit_speed(speed_pct)
            actual_speed = (limited_speed_pct / 100.0) * 1.5

            # Reset locator to origin
            await self.reset_locator()
            await asyncio.sleep(0.1)

            # Ensure locator is streaming
            from ..hardware.sensor_stream_manager import SensorStreamManager
            sensor_manager = SensorStreamManager(
                rvr=self._connection_manager.rvr,
                state_manager=self._connection_manager._state_manager
            )
            await sensor_manager.ensure_locator_streaming(interval_ms=50)

            poll_interval = 0.05
            distance_traveled = 0.0

            while True:
                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > timeout_seconds:
                    await self.stop()
                    logger.warning("drive_backward_timeout", distance=distance, traveled=distance_traveled)
                    return {
                        "success": False,
                        "error": "Timeout reached",
                        "distance_traveled": distance_traveled,
                        "target_distance": distance,
                        "elapsed_seconds": elapsed
                    }

                # Check emergency stop
                await self._safety_monitor.check_emergency_stop()

                # Get current position from locator
                position = await sensor_manager.get_locator_position(timeout=0.5)

                if position is None:
                    # Keep driving while waiting for sensor data
                    async def drive_cmd():
                        await self._connection_manager.rvr.drive_rc_si_units(
                            linear_velocity=-actual_speed,  # Negative for backward
                            yaw_angular_velocity=0
                        )

                    await self._command_queue.submit(drive_cmd, timeout=0.5)
                    await asyncio.sleep(poll_interval)
                    continue

                # Calculate distance traveled
                distance_traveled = math.sqrt(position['x']**2 + position['y']**2)

                # Check if target reached
                remaining = distance - distance_traveled
                if remaining <= tolerance:
                    await self.stop()
                    duration = time.time() - start_time
                    log_command_completed(logger, "drive_backward", duration * 1000)
                    return {
                        "success": True,
                        "distance_traveled": distance_traveled,
                        "target_distance": distance,
                        "elapsed_seconds": duration
                    }

                # Slow down near target
                current_speed = actual_speed
                if remaining < 0.05:  # Within 5cm
                    current_speed = max(0.1, actual_speed * (remaining / 0.05))

                # Drive backward
                async def drive_cmd():
                    await self._connection_manager.rvr.drive_rc_si_units(
                        linear_velocity=-current_speed,  # Negative for backward
                        yaw_angular_velocity=0
                    )

                await self._command_queue.submit(drive_cmd, timeout=0.5)
                await asyncio.sleep(poll_interval)

        except Exception as e:
            await self.stop()
            duration = time.time() - start_time
            logger.error("drive_backward_failed", error=str(e))
            return {"success": False, "error": str(e)}
