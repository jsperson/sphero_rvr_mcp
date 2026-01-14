"""Structured logging configuration using structlog.

This module sets up comprehensive structured logging that replaces
the complete absence of logging in the original implementation.
"""

import sys
import logging
import structlog
from typing import Optional


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    add_logger_name: bool = True,
    add_thread_info: bool = False,
) -> structlog.BoundLogger:
    """Configure structured logging with structlog.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ('json' or 'console')
        add_logger_name: Add logger name to each log entry
        add_thread_info: Add thread/process info to each log entry

    Returns:
        Configured logger instance
    """
    # Convert level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Build processor chain
    processors = [
        # Add log level
        structlog.stdlib.add_log_level,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # Optional: add logger name
    if add_logger_name:
        processors.append(structlog.stdlib.add_logger_name)

    # Optional: add thread/process info
    if add_thread_info:
        processors.extend([
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
        ])

    # Add exception formatting
    processors.append(structlog.processors.format_exc_info)

    # Add final renderer based on format
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Console-friendly output
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance with context binding
    """
    return structlog.get_logger(name)


# Convenience functions for common logging patterns
def log_command_submitted(logger: structlog.BoundLogger, command_type: str, **kwargs):
    """Log command submission."""
    logger.info("command_submitted", command_type=command_type, **kwargs)


def log_command_completed(logger: structlog.BoundLogger, command_type: str, duration_ms: float, **kwargs):
    """Log command completion."""
    logger.info(
        "command_completed",
        command_type=command_type,
        duration_ms=duration_ms,
        **kwargs,
    )


def log_command_failed(logger: structlog.BoundLogger, command_type: str, error: str, **kwargs):
    """Log command failure."""
    logger.error("command_failed", command_type=command_type, error=error, **kwargs)


def log_state_transition(
    logger: structlog.BoundLogger, from_state: str, to_state: str, **kwargs
):
    """Log state transition."""
    logger.info("state_transition", from_state=from_state, to_state=to_state, **kwargs)


def log_connection_event(logger: structlog.BoundLogger, event_name: str, **kwargs):
    """Log connection event."""
    logger.info("connection_event", event_name=event_name, **kwargs)


def log_sensor_event(logger: structlog.BoundLogger, sensor: str, event_name: str, **kwargs):
    """Log sensor event."""
    logger.debug("sensor_event", sensor=sensor, event_name=event_name, **kwargs)


def log_safety_event(logger: structlog.BoundLogger, event_name: str, **kwargs):
    """Log safety system event."""
    logger.warning("safety_event", event_name=event_name, **kwargs)


def log_circuit_breaker_event(logger: structlog.BoundLogger, state: str, **kwargs):
    """Log circuit breaker state change."""
    logger.warning("circuit_breaker_event", state=state, **kwargs)


# Initialize default logger
default_logger = get_logger("sphero_rvr_mcp")
