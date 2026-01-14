"""MCP tools for movement control."""

from ..services.movement_service import MovementService


def register_movement_tools(mcp, movement_service: MovementService):
    """Register movement tools with MCP server.

    Args:
        mcp: FastMCP instance
        movement_service: Movement service instance
    """

    @mcp.tool()
    async def drive_with_heading(speed: int, heading: int, reverse: bool = False) -> dict:
        """Drive the RVR at a given speed toward a heading.

        Args:
            speed: Speed 0-255 (will be limited by safety settings)
            heading: Heading 0-359 degrees (0 = forward)
            reverse: If True, drive in reverse

        Returns:
            Drive result with actual speed applied
        """
        return await movement_service.drive_with_heading(speed, heading, reverse)

    @mcp.tool()
    async def drive_tank(left_velocity: float, right_velocity: float) -> dict:
        """Drive using tank controls (independent left/right velocities).

        Args:
            left_velocity: Left track velocity in m/s (-1.5 to 1.5)
            right_velocity: Right track velocity in m/s (-1.5 to 1.5)

        Returns:
            Drive result with actual velocities applied
        """
        return await movement_service.drive_tank(left_velocity, right_velocity)

    @mcp.tool()
    async def drive_rc(linear_velocity: float, yaw_velocity: float) -> dict:
        """Drive using RC-style controls (linear + yaw).

        Args:
            linear_velocity: Forward/backward velocity in m/s (-1.5 to 1.5)
            yaw_velocity: Turning rate in degrees/second

        Returns:
            Drive result with actual velocities applied
        """
        return await movement_service.drive_rc(linear_velocity, yaw_velocity)

    @mcp.tool()
    async def stop(deceleration: float = None) -> dict:
        """Stop the RVR.

        Args:
            deceleration: Optional custom deceleration rate

        Returns:
            Stop result
        """
        return await movement_service.stop(deceleration)

    @mcp.tool()
    async def emergency_stop() -> dict:
        """Execute emergency stop - immediately stops motors and blocks further movement.

        Call clear_emergency_stop() to allow movement again.

        Returns:
            Emergency stop result
        """
        return await movement_service.emergency_stop()

    @mcp.tool()
    async def clear_emergency_stop() -> dict:
        """Clear emergency stop to allow movement again.

        Returns:
            Result of clearing emergency stop
        """
        return await movement_service.clear_emergency_stop()

    @mcp.tool()
    async def reset_yaw() -> dict:
        """Reset yaw - set current heading as 0 degrees.

        Returns:
            Result
        """
        return await movement_service.reset_yaw()

    @mcp.tool()
    async def reset_locator() -> dict:
        """Reset locator - set current position as origin (0, 0).

        Returns:
            Result
        """
        return await movement_service.reset_locator()
