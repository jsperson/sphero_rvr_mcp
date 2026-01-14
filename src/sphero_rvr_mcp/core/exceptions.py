"""Exception hierarchy for Sphero RVR MCP server.

This module defines a comprehensive exception hierarchy that replaces
the silent failures in the original implementation.
"""


class RVRError(Exception):
    """Base exception for all RVR-related errors."""

    pass


class ConnectionError(RVRError):
    """Connection-related errors.

    Raised when connection operations fail, including:
    - Failed to establish connection
    - Connection lost during operation
    - Serial port unavailable
    - RVR not responding to wake
    """

    pass


class CommandError(RVRError):
    """Command execution errors.

    Raised when command operations fail during:
    - Command validation
    - Command execution
    - Response handling
    """

    pass


class CommandTimeoutError(CommandError):
    """Command timed out waiting for execution or response."""

    pass


class CommandQueueFullError(CommandError):
    """Command queue at capacity - backpressure activated."""

    pass


class SensorError(RVRError):
    """Sensor-related errors.

    Raised when sensor operations fail:
    - Sensor streaming failed to start
    - Sensor query timeout
    - Invalid sensor data
    - Sensor not available
    """

    pass


class SafetyError(RVRError):
    """Safety system errors.

    Raised when safety constraints are violated:
    - Emergency stop active
    - Speed limit validation failure
    - Invalid safety configuration
    """

    pass


class CircuitBreakerOpenError(RVRError):
    """Circuit breaker is open - connection unhealthy.

    Raised when attempting to execute operations while the circuit
    breaker is in OPEN state, indicating the RVR is unresponsive.
    """

    pass


class StateTransitionError(RVRError):
    """Invalid state transition attempted.

    Raised when code attempts an invalid state transition in the
    connection state machine or safety state.
    """

    pass


class ConfigurationError(RVRError):
    """Configuration validation error.

    Raised when configuration values are invalid:
    - Out of range values
    - Mutually exclusive settings
    - Missing required configuration
    """

    pass
