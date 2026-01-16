"""Simplified command queue - serialization with asyncio.Lock.

This module provides simple command serialization to prevent concurrent
SDK calls from interfering with each other. All commands execute sequentially.
"""

import asyncio
from typing import Any, Callable

from .exceptions import CommandTimeoutError


class CommandQueue:
    """Simple command serialization with asyncio.Lock.

    Features:
    - Sequential execution (no concurrent SDK calls)
    - Per-command timeout enforcement
    - Simple and maintainable
    """

    def __init__(self, max_queue_size: int = 100):
        """Initialize command queue.

        Args:
            max_queue_size: Ignored, kept for API compatibility
        """
        self._lock = asyncio.Lock()

    async def start(self):
        """No-op for API compatibility."""
        pass

    async def stop(self):
        """No-op for API compatibility."""
        pass

    async def submit(
        self,
        command: Callable,
        *args,
        priority=None,  # Ignored, kept for API compatibility
        timeout: float = 5.0,
        **kwargs,
    ) -> Any:
        """Execute command with lock serialization.

        Args:
            command: Async callable to execute
            *args: Positional arguments for command
            priority: Ignored (all commands treated equally)
            timeout: Maximum time to wait for command execution
            **kwargs: Keyword arguments for command

        Returns:
            Result from command execution

        Raises:
            CommandTimeoutError: Command timed out
            Exception: Any exception raised by the command
        """
        async with self._lock:
            try:
                result = await asyncio.wait_for(
                    command(*args, **kwargs),
                    timeout=timeout
                )
                return result
            except asyncio.TimeoutError:
                raise CommandTimeoutError(f"Command timed out after {timeout}s")
