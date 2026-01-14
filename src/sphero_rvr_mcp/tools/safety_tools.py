"""MCP tools for safety control."""

from ..services.safety_service import SafetyService


def register_safety_tools(mcp, safety_service: SafetyService):
    """Register safety tools with MCP server.

    Args:
        mcp: FastMCP instance
        safety_service: Safety service instance
    """

    @mcp.tool()
    async def get_safety_status() -> dict:
        """Get safety system status.

        Returns:
            Current safety settings and state
        """
        return await safety_service.get_safety_status()

    @mcp.tool()
    async def set_speed_limit(max_speed_percent: float) -> dict:
        """Set maximum speed limit.

        Args:
            max_speed_percent: Speed limit 0-100 (percentage of max speed)

        Returns:
            New speed limit
        """
        return await safety_service.set_speed_limit(max_speed_percent)

    @mcp.tool()
    async def set_command_timeout(timeout_seconds: float) -> dict:
        """Set auto-stop timeout for movement commands.

        If no movement command is received within this time, the RVR will stop.
        Set to 0 to disable timeout.

        Args:
            timeout_seconds: Timeout in seconds (0 to disable)

        Returns:
            New timeout setting
        """
        return await safety_service.set_command_timeout(timeout_seconds)
