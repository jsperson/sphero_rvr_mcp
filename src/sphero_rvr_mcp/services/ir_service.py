"""IR communication service."""

from ..core.command_queue import CommandQueue
from ..hardware.connection_manager import ConnectionManager
from ..observability.logging import get_logger

logger = get_logger(__name__)


class IRService:
    """IR communication operations."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        command_queue: CommandQueue,
    ):
        """Initialize IR service.

        Args:
            connection_manager: Connection manager
            command_queue: Command queue
        """
        self._connection_manager = connection_manager
        self._command_queue = command_queue

    async def send_ir_message(self, code: int, strength: int = 32) -> dict:
        """Send IR message.

        Args:
            code: IR code 0-7
            strength: Signal strength 0-64

        Returns:
            Result
        """
        try:
            await self._connection_manager.ensure_connected()

            # Validate
            code = max(0, min(7, code))
            strength = max(0, min(64, strength))

            async def ir_command():
                await self._connection_manager.rvr.send_infrared_message(
                    infrared_code=code, infrared_strength=strength
                )

            await self._command_queue.submit(
                ir_command, timeout=1.0
            )

            return {"success": True, "code": code, "strength": strength}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def start_ir_broadcasting(self, far_code: int, near_code: int) -> dict:
        """Start IR broadcasting.

        Args:
            far_code: IR code for far detection 0-7
            near_code: IR code for near detection 0-7

        Returns:
            Result
        """
        try:
            await self._connection_manager.ensure_connected()

            far_code = max(0, min(7, far_code))
            near_code = max(0, min(7, near_code))

            async def ir_command():
                await self._connection_manager.rvr.start_robot_to_robot_infrared_broadcasting(
                    far_code=far_code, near_code=near_code
                )

            await self._command_queue.submit(
                ir_command, timeout=1.0
            )

            return {"success": True, "far_code": far_code, "near_code": near_code}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def stop_ir_broadcasting(self) -> dict:
        """Stop IR broadcasting.

        Returns:
            Result
        """
        try:
            await self._connection_manager.ensure_connected()

            async def ir_command():
                await self._connection_manager.rvr.stop_robot_to_robot_infrared_broadcasting()

            await self._command_queue.submit(
                ir_command, timeout=1.0
            )

            return {"success": True, "message": "IR broadcasting stopped"}

        except Exception as e:
            return {"success": False, "error": str(e)}
