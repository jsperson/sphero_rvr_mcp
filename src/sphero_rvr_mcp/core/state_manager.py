"""Atomic state management for system state.

This module provides thread-safe state management that replaces the
race-prone global mutable state in the original implementation.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
from copy import deepcopy

from .exceptions import StateTransitionError


class ConnectionState(Enum):
    """Connection state machine states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class SystemState:
    """Thread-safe system state with atomic operations."""

    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    last_state_change: float = field(default_factory=time.time)

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # Valid state transitions
    _VALID_TRANSITIONS: Dict[ConnectionState, list[ConnectionState]] = field(
        default_factory=lambda: {
            ConnectionState.DISCONNECTED: [ConnectionState.CONNECTING],
            ConnectionState.CONNECTING: [
                ConnectionState.CONNECTED,
                ConnectionState.ERROR,
                ConnectionState.DISCONNECTED,
            ],
            ConnectionState.CONNECTED: [ConnectionState.RECONNECTING, ConnectionState.DISCONNECTED],
            ConnectionState.RECONNECTING: [
                ConnectionState.CONNECTED,
                ConnectionState.ERROR,
                ConnectionState.DISCONNECTED,
            ],
            ConnectionState.ERROR: [ConnectionState.DISCONNECTED, ConnectionState.RECONNECTING],
        },
        init=False,
        repr=False,
    )

    async def transition_connection_state(self, new_state: ConnectionState) -> bool:
        """Atomically transition connection state with validation.

        Args:
            new_state: Target state

        Returns:
            True if transition successful, False if invalid

        Raises:
            StateTransitionError: If transition is invalid
        """
        async with self._lock:
            valid_next_states = self._VALID_TRANSITIONS.get(self.connection_state, [])

            if new_state not in valid_next_states:
                raise StateTransitionError(
                    f"Invalid transition from {self.connection_state.value} to {new_state.value}"
                )

            self.connection_state = new_state
            self.last_state_change = time.time()
            return True

    async def get_connection_state(self) -> ConnectionState:
        """Get current connection state atomically."""
        async with self._lock:
            return self.connection_state

    async def snapshot(self) -> dict:
        """Get thread-safe snapshot of system state."""
        async with self._lock:
            return {
                "connection_state": self.connection_state.value,
                "time_in_state_seconds": time.time() - self.last_state_change,
            }


@dataclass
class ConnectionInfo:
    """Connection information state."""

    firmware_version: Optional[str] = None
    mac_address: Optional[str] = None
    serial_port: Optional[str] = None
    baud_rate: Optional[int] = None
    connected_at: Optional[float] = None

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def set_connection_info(
        self,
        firmware_version: str,
        mac_address: str,
        serial_port: str,
        baud_rate: int,
    ):
        """Set connection information atomically."""
        async with self._lock:
            self.firmware_version = firmware_version
            self.mac_address = mac_address
            self.serial_port = serial_port
            self.baud_rate = baud_rate
            self.connected_at = time.time()

    async def clear_connection_info(self):
        """Clear connection information atomically."""
        async with self._lock:
            self.firmware_version = None
            self.mac_address = None
            self.serial_port = None
            self.baud_rate = None
            self.connected_at = None

    async def get_uptime_seconds(self) -> Optional[float]:
        """Get connection uptime in seconds."""
        async with self._lock:
            if self.connected_at is None:
                return None
            return time.time() - self.connected_at

    async def snapshot(self) -> dict:
        """Get thread-safe snapshot of connection info."""
        async with self._lock:
            uptime = None
            if self.connected_at is not None:
                uptime = time.time() - self.connected_at

            return {
                "firmware_version": self.firmware_version,
                "mac_address": self.mac_address,
                "serial_port": self.serial_port,
                "baud_rate": self.baud_rate,
                "uptime_seconds": uptime,
            }


@dataclass
class SafetyState:
    """Safety system state with atomic operations."""

    emergency_stopped: bool = False
    speed_limit_percent: float = 50.0
    command_timeout_seconds: float = 5.0
    last_command_time: Optional[float] = None

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def set_emergency_stop(self, value: bool):
        """Atomically set emergency stop flag."""
        async with self._lock:
            self.emergency_stopped = value

    async def is_emergency_stopped(self) -> bool:
        """Check if emergency stop is active."""
        async with self._lock:
            return self.emergency_stopped

    async def set_speed_limit(self, percent: float):
        """Set speed limit percentage."""
        async with self._lock:
            self.speed_limit_percent = max(0.0, min(100.0, percent))

    async def get_speed_limit(self) -> float:
        """Get current speed limit."""
        async with self._lock:
            return self.speed_limit_percent

    async def set_command_timeout(self, seconds: float):
        """Set command timeout."""
        async with self._lock:
            self.command_timeout_seconds = seconds

    async def get_command_timeout(self) -> float:
        """Get command timeout."""
        async with self._lock:
            return self.command_timeout_seconds

    async def record_command(self):
        """Record that a command was executed."""
        async with self._lock:
            self.last_command_time = time.time()

    async def get_last_command_age_ms(self) -> Optional[float]:
        """Get milliseconds since last command."""
        async with self._lock:
            if self.last_command_time is None:
                return None
            return (time.time() - self.last_command_time) * 1000.0

    async def snapshot(self) -> dict:
        """Get thread-safe snapshot of safety state."""
        async with self._lock:
            last_command_age = None
            if self.last_command_time is not None:
                last_command_age = (time.time() - self.last_command_time) * 1000.0

            return {
                "emergency_stopped": self.emergency_stopped,
                "speed_limit_percent": self.speed_limit_percent,
                "command_timeout_seconds": self.command_timeout_seconds,
                "last_command_age_ms": last_command_age,
            }


@dataclass
class SensorState:
    """Sensor streaming state."""

    streaming_active: bool = False
    streaming_sensors: list[str] = field(default_factory=list)
    streaming_interval_ms: int = 250
    sensor_data_cache: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cache_ttl_seconds: float = 2.0

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def set_streaming(self, active: bool, sensors: Optional[list[str]] = None, interval_ms: Optional[int] = None):
        """Set streaming state."""
        async with self._lock:
            self.streaming_active = active
            if sensors is not None:
                self.streaming_sensors = sensors.copy()
            if interval_ms is not None:
                self.streaming_interval_ms = interval_ms

    async def is_streaming(self) -> bool:
        """Check if streaming is active."""
        async with self._lock:
            return self.streaming_active

    async def update_cache(self, sensor: str, data: dict):
        """Update sensor data cache."""
        async with self._lock:
            self.sensor_data_cache[sensor] = {
                "data": deepcopy(data),
                "timestamp": time.time(),
            }

    async def get_cached_data(self, sensor: str) -> Optional[dict]:
        """Get cached sensor data if fresh."""
        async with self._lock:
            cached = self.sensor_data_cache.get(sensor)
            if cached is None:
                return None

            age = time.time() - cached["timestamp"]
            if age >= self.cache_ttl_seconds:
                # Stale - remove from cache
                del self.sensor_data_cache[sensor]
                return None

            return {
                "data": deepcopy(cached["data"]),
                "age_ms": age * 1000.0,
            }

    async def clear_cache(self):
        """Clear all cached sensor data."""
        async with self._lock:
            self.sensor_data_cache.clear()

    async def snapshot(self) -> dict:
        """Get thread-safe snapshot of sensor state."""
        async with self._lock:
            return {
                "streaming_active": self.streaming_active,
                "streaming_sensors": self.streaming_sensors.copy(),
                "streaming_interval_ms": self.streaming_interval_ms,
                "cached_sensors": list(self.sensor_data_cache.keys()),
            }


class StateManager:
    """Centralized state management with atomic operations.

    Replaces the global mutable state in the original implementation
    with thread-safe, atomic state management.
    """

    def __init__(self):
        """Initialize state manager."""
        self.system_state = SystemState()
        self.connection_info = ConnectionInfo()
        self.safety_state = SafetyState()
        self.sensor_state = SensorState()

    async def get_full_snapshot(self) -> dict:
        """Get thread-safe snapshot of all state."""
        return {
            "system": await self.system_state.snapshot(),
            "connection": await self.connection_info.snapshot(),
            "safety": await self.safety_state.snapshot(),
            "sensor": await self.sensor_state.snapshot(),
        }

    async def reset(self):
        """Reset all state to initial values."""
        self.system_state = SystemState()
        self.connection_info = ConnectionInfo()
        self.safety_state = SafetyState()
        self.sensor_state = SensorState()
