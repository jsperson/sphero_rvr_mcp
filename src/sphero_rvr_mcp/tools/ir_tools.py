"""MCP tools for IR communication."""

from ..services.ir_service import IRService


def register_ir_tools(mcp, ir_service: IRService):
    """Register IR tools with MCP server.

    Args:
        mcp: FastMCP instance
        ir_service: IR service instance
    """

    @mcp.tool()
    async def send_ir_message(code: int, strength: int = 32) -> dict:
        """Send an IR message.

        Args:
            code: IR code 0-7
            strength: Signal strength 0-64

        Returns:
            Result
        """
        return await ir_service.send_ir_message(code, strength)

    @mcp.tool()
    async def start_ir_broadcasting(far_code: int, near_code: int) -> dict:
        """Start IR broadcasting (for robot-to-robot communication).

        Args:
            far_code: IR code for far detection 0-7
            near_code: IR code for near detection 0-7

        Returns:
            Result
        """
        return await ir_service.start_ir_broadcasting(far_code, near_code)

    @mcp.tool()
    async def stop_ir_broadcasting() -> dict:
        """Stop IR broadcasting.

        Returns:
            Result
        """
        return await ir_service.stop_ir_broadcasting()
