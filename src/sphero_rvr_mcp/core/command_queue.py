"""Priority command queue with timeout and backpressure management.

This module implements a priority-based async command queue that eliminates
the race conditions present in the original implementation where concurrent
commands could interfere with each other.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import IntEnum

from .exceptions import CommandQueueFullError, CommandTimeoutError


class CommandPriority(IntEnum):
    """Command priority levels."""

    EMERGENCY = 0  # Emergency stop - highest priority
    HIGH = 1  # Safety-critical commands
    NORMAL = 2  # Regular movement commands
    LOW = 3  # LED control, sensor queries


@dataclass(order=True)
class CommandEntry:
    """Entry in the command queue with priority ordering."""

    priority: int
    sequence: int = field(compare=True)  # Tie-breaker for same priority
    command: Callable = field(compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    timeout: float = field(default=5.0, compare=False)
    result_future: asyncio.Future = field(default_factory=asyncio.Future, compare=False)
    submitted_at: float = field(default_factory=time.time, compare=False)
    cancelled: bool = field(default=False, compare=False)


class CommandQueue:
    """Priority queue with timeout and backpressure management.

    Features:
    - Priority-based execution (EMERGENCY > HIGH > NORMAL > LOW)
    - Per-command timeout enforcement
    - Backpressure management (rejects when full)
    - Single executor thread (eliminates races)
    - Cancellation support
    """

    def __init__(self, max_queue_size: int = 100):
        """Initialize command queue.

        Args:
            max_queue_size: Maximum number of queued commands before backpressure activates
        """
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._executor_task: Optional[asyncio.Task] = None
        self._current_command: Optional[CommandEntry] = None
        self._command_lock = asyncio.Lock()
        self._running = False
        self._sequence_counter = 0
        self._max_queue_size = max_queue_size

    async def start(self):
        """Start the command executor background task."""
        if self._running:
            return

        self._running = True
        self._executor_task = asyncio.create_task(self._executor_loop())

    async def stop(self):
        """Stop the command executor and cancel pending commands."""
        self._running = False

        if self._executor_task:
            self._executor_task.cancel()
            try:
                await self._executor_task
            except asyncio.CancelledError:
                pass

        # Cancel all pending commands
        while not self._queue.empty():
            try:
                entry = self._queue.get_nowait()
                if not entry.result_future.done():
                    entry.result_future.set_exception(
                        CommandTimeoutError("Command cancelled during queue shutdown")
                    )
            except asyncio.QueueEmpty:
                break

    async def submit(
        self,
        command: Callable,
        *args,
        priority: CommandPriority = CommandPriority.NORMAL,
        timeout: float = 5.0,
        **kwargs,
    ) -> Any:
        """Submit a command for execution with priority and timeout.

        Args:
            command: Async callable to execute
            *args: Positional arguments for command
            priority: Command priority level
            timeout: Maximum time to wait for command execution
            **kwargs: Keyword arguments for command

        Returns:
            Result from command execution

        Raises:
            CommandQueueFullError: Queue is at capacity
            CommandTimeoutError: Command timed out
            Exception: Any exception raised by the command
        """
        # Backpressure: reject if queue full
        if self._queue.full():
            raise CommandQueueFullError(
                f"Command queue at capacity ({self._max_queue_size} commands)"
            )

        # Create command entry with sequence number for tie-breaking
        self._sequence_counter += 1
        entry = CommandEntry(
            priority=priority,
            sequence=self._sequence_counter,
            command=command,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            result_future=asyncio.Future(),
        )

        # Add to queue
        await self._queue.put(entry)

        # Wait for result with timeout
        try:
            result = await asyncio.wait_for(entry.result_future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # Mark as cancelled so executor skips it
            entry.cancelled = True
            raise CommandTimeoutError(f"Command timed out after {timeout}s")

    def get_queue_depth(self) -> int:
        """Get current number of queued commands."""
        return self._queue.qsize()

    def get_current_command(self) -> Optional[dict]:
        """Get information about currently executing command."""
        if self._current_command is None:
            return None

        return {
            "priority": self._current_command.priority,
            "timeout": self._current_command.timeout,
            "age_seconds": time.time() - self._current_command.submitted_at,
        }

    async def _executor_loop(self):
        """Background task that executes commands sequentially."""
        while self._running:
            try:
                # Wait for next command
                entry = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # Skip if cancelled
                if entry.cancelled:
                    continue

                # Execute command
                self._current_command = entry

                try:
                    async with self._command_lock:
                        # Execute with timeout
                        result = await asyncio.wait_for(
                            entry.command(*entry.args, **entry.kwargs),
                            timeout=entry.timeout,
                        )

                    # Set result
                    if not entry.result_future.done():
                        entry.result_future.set_result(result)

                except asyncio.TimeoutError:
                    if not entry.result_future.done():
                        entry.result_future.set_exception(
                            CommandTimeoutError(
                                f"Command execution timed out after {entry.timeout}s"
                            )
                        )

                except Exception as e:
                    if not entry.result_future.done():
                        entry.result_future.set_exception(e)

                finally:
                    self._current_command = None

            except asyncio.TimeoutError:
                # No command available, continue waiting
                continue

            except asyncio.CancelledError:
                # Executor stopped
                break

            except Exception:
                # Unexpected error in executor loop - continue running
                continue
