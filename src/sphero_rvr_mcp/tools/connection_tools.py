"""MCP tools for connection management."""

from ..services.connection_service import ConnectionService


def register_connection_tools(mcp, connection_service: ConnectionService):
    """Register connection tools with MCP server.

    Args:
        mcp: FastMCP instance
        connection_service: Connection service instance
    """

    @mcp.tool()
    async def connect(port: str = "/dev/ttyS0", baud: int = 115200) -> dict:
        """Connect to the Sphero RVR robot and wake it up.

        Args:
            port: Serial port (default: /dev/ttyS0)
            baud: Baud rate (default: 115200)

        Returns:
            Connection result with success status and message
        """
        try:
            return await connection_service.connect(port, baud)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    async def disconnect() -> dict:
        """Safely disconnect from the RVR.

        Returns:
            Disconnection result
        """
        try:
            return await connection_service.disconnect()
        except Exception as e:
            return {"success": False, "error": str(e)}

    @mcp.tool()
    async def get_connection_status() -> dict:
        """Get current connection status.

        Returns:
            Connection status including uptime and firmware version
        """
        try:
            return await connection_service.get_connection_status()
        except Exception as e:
            return {"success": False, "error": str(e)}
