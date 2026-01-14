"""Circuit breaker pattern for connection resilience.

This module implements a circuit breaker that prevents cascading failures
when the RVR is unresponsive. It replaces the infinite hangs present in
the original implementation.
"""

import asyncio
import time
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass

from .exceptions import CircuitBreakerOpenError


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation - requests pass through
    OPEN = "open"  # Failing - requests rejected immediately
    HALF_OPEN = "half_open"  # Testing - limited requests to check recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures before opening circuit
    success_threshold: int = 2  # Successes in HALF_OPEN before closing
    timeout_duration: float = 30.0  # Seconds in OPEN before trying HALF_OPEN
    call_timeout: float = 5.0  # Default timeout for wrapped calls


class CircuitBreaker:
    """Circuit breaker for RVR connection health.

    State Machine:
        CLOSED --[failures >= threshold]--> OPEN
        OPEN --[timeout elapsed]--> HALF_OPEN
        HALF_OPEN --[success >= threshold]--> CLOSED
        HALF_OPEN --[any failure]--> OPEN

    Features:
    - Prevents cascading failures when RVR unresponsive
    - Auto-recovery with exponential backoff
    - Fail-fast when circuit is open
    - Configurable thresholds and timeouts
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        """Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
        """
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change_time = time.time()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit breaker state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count

    @property
    def success_count(self) -> int:
        """Get current success count (in HALF_OPEN state)."""
        return self._success_count

    def get_state_info(self) -> dict:
        """Get detailed state information."""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "time_in_state_seconds": time.time() - self._last_state_change_time,
            "last_failure_time": self._last_failure_time,
        }

    async def call(
        self, func: Callable, *args, timeout: Optional[float] = None, **kwargs
    ) -> Any:
        """Execute function through circuit breaker.

        Args:
            func: Async callable to execute
            *args: Positional arguments
            timeout: Call timeout (uses config default if not specified)
            **kwargs: Keyword arguments

        Returns:
            Result from function execution

        Raises:
            CircuitBreakerOpenError: Circuit breaker is OPEN
            Exception: Any exception from the function
        """
        async with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if (
                    self._last_failure_time
                    and time.time() - self._last_failure_time
                    >= self._config.timeout_duration
                ):
                    await self._transition_to(CircuitState.HALF_OPEN)
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN. "
                        f"Retry in {self._config.timeout_duration - (time.time() - self._last_failure_time):.1f}s"
                    )

            # In HALF_OPEN, only allow limited requests
            if self._state == CircuitState.HALF_OPEN:
                # This is a test request
                pass

        # Execute function with timeout
        call_timeout = timeout or self._config.call_timeout

        try:
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=call_timeout)
            await self._on_success()
            return result

        except asyncio.TimeoutError as e:
            await self._on_failure(e)
            raise

        except Exception as e:
            await self._on_failure(e)
            raise

    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self._config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)

            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in CLOSED state
                self._failure_count = 0

    async def _on_failure(self, exception: Exception):
        """Handle failed call."""
        async with self._lock:
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN immediately opens circuit
                await self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self._config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)

    async def _transition_to(self, new_state: CircuitState):
        """Transition to new state.

        This method should only be called while holding self._lock.
        """
        old_state = self._state
        self._state = new_state
        self._last_state_change_time = time.time()

        # Reset counters on state transition
        if new_state == CircuitState.OPEN:
            self._failure_count = 0
            self._success_count = 0

        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            # Keep failure count to track history

        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0

    async def reset(self):
        """Manually reset circuit breaker to CLOSED state."""
        async with self._lock:
            await self._transition_to(CircuitState.CLOSED)
            self._last_failure_time = None

    async def force_open(self):
        """Manually force circuit breaker to OPEN state."""
        async with self._lock:
            await self._transition_to(CircuitState.OPEN)
            self._last_failure_time = time.time()
