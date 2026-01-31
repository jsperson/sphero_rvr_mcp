"""Serial dispatcher for request-response matching and notification handling.

This module implements SDK-style communication patterns:
- Sequence number matching for request-response pairs
- Background reader thread for continuous serial monitoring
- Notification handler registration for async events
"""

import logging
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

import serial

from .packet import parse_response, ParsedResponse, SOP, EOP

logger = logging.getLogger(__name__)


@dataclass
class PendingRequest:
    """A pending request waiting for a response."""
    future: Future
    did: int
    cid: int
    seq: int
    timeout: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this request has timed out."""
        return time.time() - self.created_at > self.timeout


class SerialDispatcher:
    """Dispatches serial responses to pending requests or notification handlers.

    This class provides SDK-style communication by:
    1. Running a background reader thread that continuously reads from serial
    2. Matching responses to pending requests by (did, cid, seq) tuple
    3. Routing async notifications to registered handlers

    Thread Safety:
    - All public methods are thread-safe
    - Internal state protected by locks
    """

    def __init__(self, serial_port: serial.Serial):
        """Initialize the dispatcher.

        Args:
            serial_port: Open serial port to read from
        """
        self._serial = serial_port
        self._lock = threading.Lock()

        # Pending requests: seq -> PendingRequest
        # Using seq as primary key, but we validate (did, cid) on match
        self._pending: Dict[int, PendingRequest] = {}

        # Notification handlers: (did, cid) -> callback
        self._notification_handlers: Dict[Tuple[int, int], Callable[[ParsedResponse], None]] = {}

        # Background reader thread
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()

        # Read buffer for incomplete packets
        self._buffer = bytearray()

        # Stats for debugging
        self._stats = {
            'packets_received': 0,
            'packets_dispatched': 0,
            'packets_dropped': 0,
            'timeouts': 0,
            'notifications': 0,
        }

    def start(self) -> bool:
        """Start the background reader thread.

        Returns:
            True if started successfully, False if already running
        """
        with self._lock:
            if self._running:
                return False

            self._running = True
            self._stop_event.clear()
            self._reader_thread = threading.Thread(
                target=self._reader_loop,
                name="SerialDispatcher-Reader",
                daemon=True
            )
            self._reader_thread.start()
            logger.debug("SerialDispatcher started")
            return True

    def stop(self, timeout: float = 2.0) -> bool:
        """Stop the background reader thread.

        Args:
            timeout: Maximum time to wait for thread to stop

        Returns:
            True if stopped successfully
        """
        with self._lock:
            if not self._running:
                return True

            self._running = False
            self._stop_event.set()

        # Wait for thread to finish (outside lock)
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=timeout)
            if self._reader_thread.is_alive():
                logger.warning("Reader thread did not stop within timeout")
                return False

        # Clean up pending requests
        with self._lock:
            for seq, pending in list(self._pending.items()):
                pending.future.set_exception(
                    RuntimeError("Dispatcher stopped")
                )
            self._pending.clear()
            self._buffer.clear()

        logger.debug("SerialDispatcher stopped")
        return True

    def send_and_wait(
        self,
        packet: bytes,
        did: int,
        cid: int,
        seq: int,
        timeout: float = 1.0
    ) -> Optional[ParsedResponse]:
        """Send a packet and wait for matching response.

        Args:
            packet: Complete packet to send
            did: Expected response device ID
            cid: Expected response command ID
            seq: Expected response sequence number
            timeout: Maximum time to wait for response

        Returns:
            ParsedResponse if received, None on timeout or error
        """
        future: Future[ParsedResponse] = Future()

        # Register pending request
        with self._lock:
            if not self._running:
                logger.warning("Dispatcher not running, using fallback")
                return None

            # Clean up any expired requests
            self._cleanup_expired()

            # Register this request
            self._pending[seq] = PendingRequest(
                future=future,
                did=did,
                cid=cid,
                seq=seq,
                timeout=timeout
            )

        try:
            # Send the packet
            self._serial.write(packet)
            self._serial.flush()

            # Wait for response
            try:
                response = future.result(timeout=timeout)
                return response
            except TimeoutError:
                with self._lock:
                    self._stats['timeouts'] += 1
                    self._pending.pop(seq, None)
                logger.debug(f"Timeout waiting for response: did={did:#x}, cid={cid:#x}, seq={seq}")
                return None

        except Exception as e:
            with self._lock:
                self._pending.pop(seq, None)
            logger.error(f"Error in send_and_wait: {e}")
            return None

    def register_notification_handler(
        self,
        did: int,
        cid: int,
        handler: Callable[[ParsedResponse], None]
    ) -> None:
        """Register a handler for async notifications.

        Args:
            did: Device ID to handle
            cid: Command ID to handle
            handler: Callback function receiving ParsedResponse
        """
        with self._lock:
            self._notification_handlers[(did, cid)] = handler
            logger.debug(f"Registered notification handler: did={did:#x}, cid={cid:#x}")

    def unregister_notification_handler(self, did: int, cid: int) -> bool:
        """Unregister a notification handler.

        Args:
            did: Device ID
            cid: Command ID

        Returns:
            True if handler was removed, False if not found
        """
        with self._lock:
            if (did, cid) in self._notification_handlers:
                del self._notification_handlers[(did, cid)]
                logger.debug(f"Unregistered notification handler: did={did:#x}, cid={cid:#x}")
                return True
            return False

    def get_stats(self) -> dict:
        """Get dispatcher statistics."""
        with self._lock:
            return dict(self._stats)

    def _reader_loop(self) -> None:
        """Background reader thread main loop."""
        logger.debug("Reader loop started")

        while not self._stop_event.is_set():
            try:
                # Check if serial is still open
                if not self._serial or not self._serial.is_open:
                    logger.warning("Serial port closed, stopping reader")
                    break

                # Read available data (non-blocking with short timeout)
                if self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting)
                    if data:
                        self._process_data(data)
                else:
                    # Small sleep to avoid busy-waiting
                    time.sleep(0.001)

            except serial.SerialException as e:
                if not self._stop_event.is_set():
                    logger.error(f"Serial error in reader loop: {e}")
                break
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"Error in reader loop: {e}")
                # Continue on other errors
                time.sleep(0.01)

        logger.debug("Reader loop stopped")

    def _process_data(self, data: bytes) -> None:
        """Process incoming data, extract and dispatch complete packets."""
        self._buffer.extend(data)

        # Process all complete packets in buffer
        while True:
            packet_start = -1
            packet_end = -1

            # Find SOP
            try:
                packet_start = self._buffer.index(SOP)
            except ValueError:
                # No SOP found, clear buffer
                self._buffer.clear()
                return

            # Find EOP after SOP
            try:
                packet_end = self._buffer.index(EOP, packet_start + 1)
            except ValueError:
                # No complete packet yet
                # Keep data from SOP onwards, discard anything before
                if packet_start > 0:
                    del self._buffer[:packet_start]
                return

            # Extract complete packet
            packet_bytes = bytes(self._buffer[packet_start:packet_end + 1])

            # Remove packet from buffer
            del self._buffer[:packet_end + 1]

            # Parse and dispatch
            try:
                response = parse_response(packet_bytes)
                with self._lock:
                    self._stats['packets_received'] += 1
                self._dispatch_response(response)
            except ValueError as e:
                logger.debug(f"Failed to parse packet: {e}")
                # Continue processing remaining buffer

    def _dispatch_response(self, response: ParsedResponse) -> None:
        """Route a response to pending request or notification handler."""
        with self._lock:
            # First, check if this matches a pending request
            pending = self._pending.get(response.seq)
            if pending:
                # Verify did/cid match
                if pending.did == response.did and pending.cid == response.cid:
                    del self._pending[response.seq]
                    self._stats['packets_dispatched'] += 1
                    # Set result outside lock to avoid deadlock
                    pending.future.set_result(response)
                    return
                else:
                    # Seq matches but did/cid don't - possible collision
                    logger.debug(
                        f"Seq collision: expected did={pending.did:#x}, cid={pending.cid:#x}, "
                        f"got did={response.did:#x}, cid={response.cid:#x}"
                    )

            # Check for notification handler
            handler = self._notification_handlers.get((response.did, response.cid))
            if handler:
                self._stats['notifications'] += 1

        # Call handler outside lock
        if handler:
            try:
                handler(response)
            except Exception as e:
                logger.error(f"Error in notification handler: {e}")
        else:
            # No matching pending request or handler
            with self._lock:
                self._stats['packets_dropped'] += 1
            logger.debug(
                f"Dropped packet: did={response.did:#x}, cid={response.cid:#x}, seq={response.seq}"
            )

    def _cleanup_expired(self) -> None:
        """Clean up expired pending requests. Must be called with lock held."""
        expired = [
            seq for seq, pending in self._pending.items()
            if pending.is_expired()
        ]
        for seq in expired:
            pending = self._pending.pop(seq)
            self._stats['timeouts'] += 1
            try:
                pending.future.set_exception(TimeoutError("Request timed out"))
            except Exception:
                pass  # Future might already be done
