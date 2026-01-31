"""Movement tracking and completion detection.

This module provides movement completion detection by listening for
RVR's XY position drive result notifications instead of guessing
completion time with sleep().
"""

import logging
import threading
import time
from concurrent.futures import Future
from typing import Optional

from .packet import ParsedResponse, DID_DRIVE

logger = logging.getLogger(__name__)

# Command ID for XY position drive result notification
# This is sent by RVR when drive_to_position_si completes
CID_XY_POSITION_DRIVE_RESULT_NOTIFY = 0x3B


class MovementTracker:
    """Tracks movement commands and waits for completion notifications.

    The RVR sends an XY position drive result notification when
    drive_to_position_si (and similar commands) complete. This class
    registers a notification handler and provides Future-based waiting.

    Usage:
        tracker = MovementTracker()
        tracker.register_with_dispatcher(dispatcher)

        # Start a movement
        future = tracker.start_movement(timeout=5.0)
        ds.drive_to_position_si(...)

        # Wait for completion
        result = tracker.wait_for_completion(timeout=5.0)
    """

    def __init__(self):
        """Initialize the movement tracker."""
        self._lock = threading.Lock()
        self._current_movement: Optional[Future] = None
        self._movement_start_time: float = 0.0
        self._last_result: Optional[dict] = None

        # Stats
        self._stats = {
            'movements_started': 0,
            'movements_completed': 0,
            'movements_timed_out': 0,
        }

    def register_with_dispatcher(self, dispatcher) -> None:
        """Register notification handler with the dispatcher.

        Args:
            dispatcher: SerialDispatcher instance
        """
        dispatcher.register_notification_handler(
            DID_DRIVE,
            CID_XY_POSITION_DRIVE_RESULT_NOTIFY,
            self._on_movement_complete
        )
        logger.debug("MovementTracker registered with dispatcher")

    def unregister_from_dispatcher(self, dispatcher) -> None:
        """Unregister notification handler from the dispatcher.

        Args:
            dispatcher: SerialDispatcher instance
        """
        dispatcher.unregister_notification_handler(
            DID_DRIVE,
            CID_XY_POSITION_DRIVE_RESULT_NOTIFY
        )
        logger.debug("MovementTracker unregistered from dispatcher")

    def start_movement(self, timeout: float = 10.0) -> Future:
        """Start tracking a new movement.

        Call this BEFORE sending the movement command.

        Args:
            timeout: Maximum time to wait for completion

        Returns:
            Future that will be resolved when movement completes
        """
        with self._lock:
            # Cancel any existing movement
            if self._current_movement and not self._current_movement.done():
                self._current_movement.set_exception(
                    RuntimeError("Movement cancelled by new movement")
                )

            self._current_movement = Future()
            self._movement_start_time = time.time()
            self._stats['movements_started'] += 1

            return self._current_movement

    def wait_for_completion(
        self,
        timeout: float = 10.0,
        fallback_time: Optional[float] = None
    ) -> bool:
        """Wait for the current movement to complete.

        Args:
            timeout: Maximum time to wait for notification
            fallback_time: If notification doesn't arrive, wait this long
                          as a fallback (None = no fallback, return False)

        Returns:
            True if movement completed (notification received),
            False if timed out
        """
        with self._lock:
            future = self._current_movement
            if not future:
                logger.warning("No movement in progress")
                return False

        try:
            result = future.result(timeout=timeout)
            with self._lock:
                self._stats['movements_completed'] += 1
            logger.debug(f"Movement completed: {result}")
            return True

        except (TimeoutError, Exception) as e:
            # Handle both TimeoutError and concurrent.futures.TimeoutError
            # Also catches any other exceptions
            is_timeout = isinstance(e, TimeoutError) or type(e).__name__ == 'TimeoutError'

            if is_timeout:
                with self._lock:
                    self._stats['movements_timed_out'] += 1

                if fallback_time is not None:
                    # Calculate remaining fallback time
                    elapsed = time.time() - self._movement_start_time
                    remaining = fallback_time - elapsed
                    if remaining > 0:
                        logger.debug(f"Movement notification timeout, using fallback sleep: {remaining:.2f}s")
                        time.sleep(remaining)
                    return True  # Assume success with fallback
                else:
                    logger.debug("Movement timed out waiting for notification")
                    return False
            else:
                logger.error(f"Error waiting for movement: {e}")
                return False

    def cancel_movement(self) -> None:
        """Cancel the current movement tracking."""
        with self._lock:
            if self._current_movement and not self._current_movement.done():
                self._current_movement.set_exception(
                    RuntimeError("Movement cancelled")
                )
            self._current_movement = None

    def get_last_result(self) -> Optional[dict]:
        """Get the result of the last completed movement."""
        with self._lock:
            return self._last_result

    def get_stats(self) -> dict:
        """Get movement tracking statistics."""
        with self._lock:
            return dict(self._stats)

    def _on_movement_complete(self, response: ParsedResponse) -> None:
        """Handle movement completion notification.

        Args:
            response: ParsedResponse from RVR
        """
        logger.debug(f"Movement complete notification: data={response.data.hex() if response.data else 'empty'}")

        # Parse result data if present
        result = {
            'completed': True,
            'duration': 0.0,
        }

        with self._lock:
            if self._movement_start_time:
                result['duration'] = time.time() - self._movement_start_time

            # Parse additional result data if present
            if response.data:
                # Result format may include:
                # - Error code (if any)
                # - Final position (x, y)
                # - Heading
                # For now, just note success
                if len(response.data) >= 1:
                    result['error_code'] = response.data[0]

            self._last_result = result

            # Complete the future
            future = self._current_movement
            if future and not future.done():
                future.set_result(result)
                self._current_movement = None
