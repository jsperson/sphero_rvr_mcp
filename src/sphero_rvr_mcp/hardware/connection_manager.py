"""Connection manager with circuit breaker integration.

This module replaces rvr_manager.py with a more robust implementation that:
- Uses circuit breaker for resilience
- Removes hard-coded sleeps (event-driven readiness)
- Uses atomic state management
- Provides comprehensive logging and metrics
"""

import asyncio
import time
from typing import Optional
import nest_asyncio

# Apply nest_asyncio to allow nested event loops (required for Sphero SDK)
nest_asyncio.apply()

# Sphero SDK imports
from sphero_sdk import SpheroRvrAsync, SerialAsyncDal

from ..core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from ..core.state_manager import StateManager, ConnectionState
from ..core.exceptions import ConnectionError as RVRConnectionError
from ..observability.logging import get_logger, log_connection_event, log_state_transition
from ..observability import metrics


logger = get_logger(__name__)


class ConnectionManager:
    """Manages RVR connection lifecycle with circuit breaker.

    Features:
    - Circuit breaker prevents infinite hangs
    - Event-driven readiness check (no hard-coded sleep)
    - Atomic state transitions
    - Comprehensive logging and metrics
    - Auto-cleanup on disconnect
    """

    def __init__(
        self,
        state_manager: StateManager,
        circuit_breaker: Optional[CircuitBreaker] = None,
        wake_timeout: float = 5.0,
        readiness_poll_interval: float = 0.1,
    ):
        """Initialize connection manager.

        Args:
            state_manager: Centralized state management
            circuit_breaker: Circuit breaker (creates default if not provided)
            wake_timeout: Timeout for RVR wake operation
            readiness_poll_interval: Interval for readiness polling
        """
        self._state_manager = state_manager
        self._circuit_breaker = circuit_breaker or CircuitBreaker(CircuitBreakerConfig())
        self._wake_timeout = wake_timeout
        self._readiness_poll_interval = readiness_poll_interval

        self._rvr: Optional[SpheroRvrAsync] = None
        self._dal: Optional[SerialAsyncDal] = None

    @property
    def rvr(self) -> Optional[SpheroRvrAsync]:
        """Get RVR SDK instance."""
        return self._rvr

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Get circuit breaker instance."""
        return self._circuit_breaker

    async def connect(self, port: str, baud_rate: int) -> dict:
        """Connect to RVR with event-driven readiness check.

        This replaces the hard-coded 2-second sleep with polling.

        Args:
            port: Serial port path
            baud_rate: Baud rate

        Returns:
            Connection result with firmware version and MAC address

        Raises:
            RVRConnectionError: Connection failed
        """
        # Validate state transition
        current_state = await self._state_manager.system_state.get_connection_state()
        if current_state != ConnectionState.DISCONNECTED:
            raise RVRConnectionError(
                f"Cannot connect from state {current_state.value}. Must be DISCONNECTED."
            )

        # Transition to CONNECTING
        await self._state_manager.system_state.transition_connection_state(
            ConnectionState.CONNECTING
        )
        metrics.update_connection_state("connecting")
        log_state_transition(logger, "disconnected", "connecting")

        try:
            # Get current event loop
            loop = asyncio.get_running_loop()

            # Create serial DAL with loop, device, and baud rate
            self._dal = SerialAsyncDal(
                loop=loop,
                device=port,
                baud=baud_rate
            )
            logger.info("serial_dal_created", port=port, baud_rate=baud_rate)

            # Create RVR instance
            self._rvr = SpheroRvrAsync(dal=self._dal)

            # Wake RVR through circuit breaker with timeout
            async def wake_operation():
                """Wake operation to execute through circuit breaker."""
                await self._rvr.wake()

            await self._circuit_breaker.call(
                wake_operation,
                timeout=self._wake_timeout,
            )

            log_connection_event(logger, "rvr_wake_sent")

            # Wait for RVR to be ready (event-driven, not sleep)
            await self._wait_for_ready(timeout=self._wake_timeout)

            # Query firmware version with timeout (optional - don't block connection)
            try:
                fw_response = await asyncio.wait_for(
                    self._rvr.get_battery_percentage(),  # Use battery query as connectivity test
                    timeout=2.0,
                )
                # Firmware version query is unreliable across SDK versions, set to unknown
                firmware_version = "unknown"
                logger.debug("firmware_version_query_skipped", reason="sdk_api_compatibility")
            except Exception as e:
                firmware_version = "unknown"
                logger.warning("connectivity_check_failed", error=str(e))

            # Query MAC address with timeout (optional - don't block connection)
            try:
                mac_response = await asyncio.wait_for(
                    self._rvr.get_bluetooth_advertising_name(),
                    timeout=2.0,
                )
                mac_address = mac_response.get("name", "unknown")
            except Exception as e:
                mac_address = "unknown"
                logger.warning("mac_address_query_failed", error=str(e))

            # Store connection info
            await self._state_manager.connection_info.set_connection_info(
                firmware_version=firmware_version,
                mac_address=mac_address,
                serial_port=port,
                baud_rate=baud_rate,
            )

            # Transition to CONNECTED
            await self._state_manager.system_state.transition_connection_state(
                ConnectionState.CONNECTED
            )

            metrics.update_connection_state("connected")
            metrics.connection_attempts_total.labels(result="success").inc()
            metrics.update_system_info(firmware_version, mac_address)

            log_connection_event(
                logger,
                "connected",
                firmware_version=firmware_version,
                mac_address=mac_address,
                port=port,
            )

            return {
                "success": True,
                "firmware_version": firmware_version,
                "mac_address": mac_address,
                "message": "Connected successfully",
            }

        except Exception as e:
            # Transition to ERROR
            await self._state_manager.system_state.transition_connection_state(
                ConnectionState.ERROR
            )
            metrics.update_connection_state("error")
            metrics.connection_attempts_total.labels(result="failure").inc()
            metrics.record_error(type(e).__name__)

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
            if self._rvr is not None:
                try:
                    await asyncio.wait_for(self._rvr.drive_stop(), timeout=2.0)
                except Exception as e:
                    logger.warning("motor_stop_failed_during_disconnect", error=str(e))

            # Cleanup resources
            await self._cleanup()

            # Transition to DISCONNECTED
            await self._state_manager.system_state.transition_connection_state(
                ConnectionState.DISCONNECTED
            )
            await self._state_manager.connection_info.clear_connection_info()

            metrics.update_connection_state("disconnected")
            log_connection_event(logger, "disconnected")

            return {"success": True, "message": "Disconnected successfully"}

        except Exception as e:
            logger.error("disconnect_failed", error=str(e))
            metrics.record_error(type(e).__name__)

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

        if self._rvr is None:
            raise RVRConnectionError("RVR instance is None despite CONNECTED state")

    async def _wait_for_ready(self, timeout: float):
        """Poll for RVR readiness instead of sleeping.

        This replaces the hard-coded `await asyncio.sleep(2)` in the original.

        Args:
            timeout: Maximum time to wait for readiness

        Raises:
            RVRConnectionError: RVR failed to become ready
        """
        start = time.time()

        while time.time() - start < timeout:
            try:
                # Try a lightweight query to verify readiness
                await asyncio.wait_for(
                    self._rvr.get_battery_percentage(),
                    timeout=0.5,
                )
                # Success - RVR is ready
                log_connection_event(logger, "rvr_ready", elapsed_ms=(time.time() - start) * 1000)
                return

            except asyncio.TimeoutError:
                # Not ready yet, continue polling
                await asyncio.sleep(self._readiness_poll_interval)

            except Exception as e:
                # Other error - not ready
                logger.debug("readiness_check_failed", error=str(e))
                await asyncio.sleep(self._readiness_poll_interval)

        raise RVRConnectionError(
            f"RVR failed to become ready within {timeout}s"
        )

    async def _cleanup(self):
        """Cleanup RVR and DAL resources."""
        if self._rvr is not None:
            try:
                await asyncio.wait_for(self._rvr.close(), timeout=2.0)
            except Exception as e:
                logger.warning("rvr_close_failed", error=str(e))
            finally:
                self._rvr = None

        if self._dal is not None:
            try:
                # DAL cleanup if needed
                pass
            except Exception as e:
                logger.warning("dal_cleanup_failed", error=str(e))
            finally:
                self._dal = None
