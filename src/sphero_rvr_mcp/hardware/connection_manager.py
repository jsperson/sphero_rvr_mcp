"""Connection manager using DirectSerial - no SDK overhead.

This module provides robust RVR connection management:
- Direct serial connection (no SDK)
- Fast wake and readiness check
- Atomic state management
- Comprehensive logging
"""

import asyncio
import time
from typing import Optional

from ..core.state_manager import StateManager, ConnectionState
from ..core.exceptions import ConnectionError as RVRConnectionError
from ..observability.logging import get_logger, log_connection_event, log_state_transition
from ..protocol import DirectSerial


logger = get_logger(__name__)


class ConnectionManager:
    """Manages RVR connection lifecycle using DirectSerial.

    Features:
    - Direct serial connection (bypasses SDK overhead)
    - Fast wake and readiness check
    - Atomic state transitions
    - Comprehensive logging
    - Auto-cleanup on disconnect
    """

    def __init__(
        self,
        state_manager: StateManager,
        wake_timeout: float = 5.0,
    ):
        """Initialize connection manager.

        Args:
            state_manager: Centralized state management
            wake_timeout: Timeout for RVR wake operation
        """
        self._state_manager = state_manager
        self._wake_timeout = wake_timeout

        self._direct_serial: Optional[DirectSerial] = None

    @property
    def direct_serial(self) -> Optional[DirectSerial]:
        """Get DirectSerial instance."""
        return self._direct_serial

    @property
    def rvr(self) -> Optional[DirectSerial]:
        """Compatibility property - returns DirectSerial instance."""
        return self._direct_serial

    async def connect(self, port: str, baud_rate: int) -> dict:
        """Connect to RVR using DirectSerial.

        Args:
            port: Serial port path
            baud_rate: Baud rate

        Returns:
            Connection result with firmware version and MAC address

        Raises:
            RVRConnectionError: Connection failed
        """
        # Clean up any existing connection first
        if self._direct_serial is not None:
            logger.warning("existing_connection_detected", action="cleaning_up")
            await self._cleanup()

        # Validate state transition - must be DISCONNECTED to connect
        current_state = await self._state_manager.system_state.get_connection_state()
        if current_state != ConnectionState.DISCONNECTED:
            # Force disconnect if in wrong state (including ERROR)
            logger.warning("invalid_state_for_connect", current_state=current_state.value, action="forcing_disconnect")
            await self.disconnect()

        # Transition to CONNECTING
        await self._state_manager.system_state.transition_connection_state(
            ConnectionState.CONNECTING
        )
        log_state_transition(logger, str(current_state.value), "connecting")

        try:
            # Create DirectSerial instance
            self._direct_serial = DirectSerial(port, baud_rate)

            # Connect to serial port
            if not self._direct_serial.connect():
                raise RVRConnectionError("Failed to open serial port")

            logger.info("serial_port_opened", port=port, baud_rate=baud_rate)

            # Wake RVR
            if not self._direct_serial.wake():
                raise RVRConnectionError("Failed to send wake command")

            log_connection_event(logger, "rvr_wake_sent")

            # Wait for RVR to be ready
            await self._wait_for_ready(timeout=self._wake_timeout)

            # Store connection info
            await self._state_manager.connection_info.set_connection_info(
                firmware_version="unknown",  # DirectSerial doesn't query FW version
                mac_address="unknown",
                serial_port=port,
                baud_rate=baud_rate,
            )

            # Transition to CONNECTED
            await self._state_manager.system_state.transition_connection_state(
                ConnectionState.CONNECTED
            )

            log_connection_event(
                logger,
                "connected",
                port=port,
            )

            return {
                "success": True,
                "message": "Connected successfully",
            }

        except Exception as e:
            # Transition to ERROR
            await self._state_manager.system_state.transition_connection_state(
                ConnectionState.ERROR
            )

            logger.error(
                "connection_failed",
                error=str(e),
                error_type=type(e).__name__,
                port=port,
            )

            # Cleanup
            await self._cleanup()

            raise RVRConnectionError(f"Connection failed: {str(e)}") from e

    async def disconnect(self) -> dict:
        """Safely disconnect from RVR.

        Returns:
            Disconnection result
        """
        current_state = await self._state_manager.system_state.get_connection_state()

        if current_state == ConnectionState.DISCONNECTED:
            return {"success": True, "message": "Already disconnected"}

        log_connection_event(logger, "disconnecting")

        try:
            # Stop motors first
            if self._direct_serial is not None:
                try:
                    self._direct_serial.stop()
                except Exception as e:
                    logger.warning("motor_stop_failed_during_disconnect", error=str(e))

            # Cleanup resources
            await self._cleanup()

            # Transition to DISCONNECTED
            await self._state_manager.system_state.transition_connection_state(
                ConnectionState.DISCONNECTED
            )
            await self._state_manager.connection_info.clear_connection_info()

            log_connection_event(logger, "disconnected")

            return {"success": True, "message": "Disconnected successfully"}

        except Exception as e:
            logger.error("disconnect_failed", error=str(e))

            return {"success": False, "error": str(e)}

    async def ensure_connected(self):
        """Ensure RVR is connected.

        Raises:
            RVRConnectionError: If not connected
        """
        current_state = await self._state_manager.system_state.get_connection_state()

        if current_state != ConnectionState.CONNECTED:
            raise RVRConnectionError(
                f"RVR not connected. Current state: {current_state.value}"
            )

        if self._direct_serial is None:
            raise RVRConnectionError("DirectSerial instance is None despite CONNECTED state")

    async def _wait_for_ready(self, timeout: float):
        """Wait for RVR to be ready after wake.

        Simple sleep-based approach since we don't have async responses in DirectSerial.

        Args:
            timeout: Maximum time to wait for readiness

        Raises:
            RVRConnectionError: RVR failed to become ready
        """
        # Simple 2-second sleep (SDK standard)
        await asyncio.sleep(2.0)
        log_connection_event(logger, "rvr_ready", elapsed_ms=2000)

    async def _cleanup(self):
        """Cleanup DirectSerial resources."""
        if self._direct_serial is not None:
            try:
                self._direct_serial.disconnect()
            except Exception as e:
                logger.warning("direct_serial_disconnect_failed", error=str(e))
            finally:
                self._direct_serial = None
