"""Connection service."""

from ..hardware.connection_manager import ConnectionManager
from ..observability.logging import get_logger

logger = get_logger(__name__)


class ConnectionService:
    """Connection operations with retry support."""

    def __init__(self, connection_manager: ConnectionManager):
        """Initialize connection service.

        Args:
            connection_manager: Connection manager instance
        """
        self._connection_manager = connection_manager

    async def connect(self, port: str, baud_rate: int) -> dict:
        """Connect to RVR.

        Args:
            port: Serial port
            baud_rate: Baud rate

        Returns:
            Connection result
        """
        return await self._connection_manager.connect(port, baud_rate)

    async def disconnect(self) -> dict:
        """Disconnect from RVR.

        Returns:
            Disconnection result
        """
        return await self._connection_manager.disconnect()

    async def get_connection_status(self) -> dict:
        """Get connection status.

        Returns:
            Connection status with state and details
        """
        state_snapshot = await self._connection_manager._state_manager.get_full_snapshot()

        return {
            "success": True,
            **state_snapshot["system"],
            **state_snapshot["connection"],
        }
