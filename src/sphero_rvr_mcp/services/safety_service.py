"""Safety service."""

from ..hardware.safety_monitor import SafetyMonitor
from ..observability.logging import get_logger

logger = get_logger(__name__)


class SafetyService:
    """Safety system operations."""

    def __init__(self, safety_monitor: SafetyMonitor):
        """Initialize safety service.

        Args:
            safety_monitor: Safety monitor instance
        """
        self._safety_monitor = safety_monitor

    async def get_safety_status(self) -> dict:
        """Get safety status.

        Returns:
            Safety status
        """
        return await self._safety_monitor.get_safety_status()

    async def set_speed_limit(self, max_speed_percent: float) -> dict:
        """Set speed limit.

        Args:
            max_speed_percent: Maximum speed percentage 0-100

        Returns:
            Result
        """
        return await self._safety_monitor.set_speed_limit(max_speed_percent)

    async def set_command_timeout(self, timeout_seconds: float) -> dict:
        """Set command timeout.

        Args:
            timeout_seconds: Timeout in seconds (0 to disable)

        Returns:
            Result
        """
        return await self._safety_monitor.set_command_timeout(timeout_seconds)
