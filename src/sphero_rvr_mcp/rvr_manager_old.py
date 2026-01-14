"""RVR connection lifecycle management."""

import asyncio
import time
from enum import Enum
from typing import Optional

import nest_asyncio
nest_asyncio.apply()

from .config import RvrConfig


class RvrConnectionState(Enum):
    """Connection state machine states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class RvrManager:
    """Manages RVR connection lifecycle.

    Handles connecting, disconnecting, and reconnecting to the Sphero RVR.
    Wraps the SpheroRvrAsync SDK client.
    """

    def __init__(self, config: RvrConfig):
        """Initialize RVR manager.

        Args:
            config: RVR configuration settings.
        """
        self._config = config
        self._rvr = None  # SpheroRvrAsync instance
        self._dal = None  # SerialAsyncDal instance
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._state = RvrConnectionState.DISCONNECTED
        self._connect_time: Optional[float] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._firmware_version: Optional[str] = None
        self._mac_address: Optional[str] = None

    @property
    def state(self) -> RvrConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if RVR is connected."""
        return self._state == RvrConnectionState.CONNECTED

    @property
    def rvr(self):
        """Get the SpheroRvrAsync instance.

        Returns:
            SpheroRvrAsync instance or None if not connected.
        """
        return self._rvr

    @property
    def uptime_seconds(self) -> Optional[float]:
        """Get connection uptime in seconds."""
        if self._connect_time is None:
            return None
        return time.time() - self._connect_time

    @property
    def firmware_version(self) -> Optional[str]:
        """Get RVR firmware version."""
        return self._firmware_version

    @property
    def mac_address(self) -> Optional[str]:
        """Get RVR MAC address."""
        return self._mac_address

    async def connect(self, port: Optional[str] = None, baud: Optional[int] = None) -> bool:
        """Connect to RVR and wake it up.

        Args:
            port: Serial port override (uses config default if None).
            baud: Baud rate override (uses config default if None).

        Returns:
            True if connection successful, False otherwise.
        """
        if self._state == RvrConnectionState.CONNECTED:
            return True

        self._state = RvrConnectionState.CONNECTING

        serial_port = port or self._config.serial.port
        baud_rate = baud or self._config.serial.baud_rate

        try:
            # Import SDK here to allow running without hardware for testing
            from sphero_sdk import SpheroRvrAsync, SerialAsyncDal

            self._loop = asyncio.get_running_loop()

            self._dal = SerialAsyncDal(
                self._loop,
                port_id=serial_port,
                baud=baud_rate
            )

            self._rvr = SpheroRvrAsync(dal=self._dal)

            timeout = self._config.wake_timeout_seconds

            # Wake up the RVR with timeout
            try:
                await asyncio.wait_for(self._rvr.wake(), timeout=timeout)
            except asyncio.TimeoutError:
                raise ConnectionError(f"RVR wake() timed out after {timeout}s - is the RVR powered on?")

            # Wait for RVR to be ready
            await asyncio.sleep(2)

            # Get system info with timeouts
            try:
                fw_response = await asyncio.wait_for(
                    self._rvr.get_main_application_version(),
                    timeout=timeout
                )
                if fw_response:
                    major = fw_response.get('major', 0)
                    minor = fw_response.get('minor', 0)
                    patch = fw_response.get('patch', 0)
                    self._firmware_version = f"{major}.{minor}.{patch}"
            except (asyncio.TimeoutError, Exception):
                self._firmware_version = "unknown"

            try:
                mac_response = await asyncio.wait_for(
                    self._rvr.get_bluetooth_advertising_name(),
                    timeout=timeout
                )
                if mac_response:
                    self._mac_address = mac_response.get('name', 'unknown')
            except (asyncio.TimeoutError, Exception):
                self._mac_address = "unknown"

            self._state = RvrConnectionState.CONNECTED
            self._connect_time = time.time()
            return True

        except Exception as e:
            self._state = RvrConnectionState.ERROR
            self._rvr = None
            self._dal = None
            raise ConnectionError(f"Failed to connect to RVR: {e}") from e

    async def disconnect(self) -> bool:
        """Safely disconnect from RVR.

        Returns:
            True if disconnection successful.
        """
        if self._state == RvrConnectionState.DISCONNECTED:
            return True

        try:
            if self._rvr is not None:
                # Stop motors
                try:
                    await self._rvr.drive_stop()
                except Exception:
                    pass

                # Close connection
                try:
                    await self._rvr.close()
                except Exception:
                    pass

            self._rvr = None
            self._dal = None
            self._state = RvrConnectionState.DISCONNECTED
            self._connect_time = None
            self._firmware_version = None
            self._mac_address = None
            return True

        except Exception as e:
            self._state = RvrConnectionState.ERROR
            raise ConnectionError(f"Error during disconnect: {e}") from e

    async def reconnect(self) -> bool:
        """Attempt to reconnect to RVR with backoff.

        Returns:
            True if reconnection successful.
        """
        self._state = RvrConnectionState.RECONNECTING

        # Try to disconnect first
        try:
            await self.disconnect()
        except Exception:
            pass

        # Attempt reconnection with exponential backoff
        for attempt in range(self._config.reconnect_max_attempts):
            backoff = self._config.reconnect_backoff_base_seconds * (2 ** attempt)
            await asyncio.sleep(backoff)

            try:
                success = await self.connect()
                if success:
                    return True
            except Exception:
                continue

        self._state = RvrConnectionState.ERROR
        return False

    def ensure_connected(self) -> None:
        """Raise exception if not connected.

        Raises:
            ConnectionError: If RVR is not connected.
        """
        if not self.is_connected:
            raise ConnectionError(
                f"RVR not connected. Current state: {self._state.value}"
            )
