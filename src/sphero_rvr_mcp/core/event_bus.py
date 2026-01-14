"""Async event bus for sensor data distribution and system events.

This module implements a pub/sub event bus that decouples sensor streaming
from data consumers, replacing the tight coupling in the original implementation.
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Dict, List
from enum import Enum


class EventType(str, Enum):
    """System event types."""

    SENSOR_DATA = "sensor_data"
    CONNECTION_STATE = "connection_state"
    SAFETY_EVENT = "safety_event"
    COMMAND_EXECUTED = "command_executed"
    ERROR = "error"


@dataclass
class Event:
    """Event published to the event bus."""

    type: EventType
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None


@dataclass
class Subscriber:
    """Event subscriber with optional filtering."""

    handler: Callable[[Event], Any]
    filter_func: Optional[Callable[[Event], bool]] = None
    subscriber_id: Optional[str] = None


class EventBus:
    """Async event bus for decoupled communication.

    Features:
    - Pub/sub pattern for sensor data and system events
    - Multiple subscribers per event type
    - Optional filtering per subscriber
    - Built-in backpressure (drops oldest events when queue full)
    - Async dispatch to prevent blocking publishers
    """

    def __init__(self, max_queue_size: int = 1000):
        """Initialize event bus.

        Args:
            max_queue_size: Maximum queued events before backpressure activates
        """
        self._subscribers: Dict[EventType, List[Subscriber]] = defaultdict(list)
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue_size)
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._running = False
        self._subscriber_counter = 0
        self._dropped_events_count = 0
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the event dispatcher background task."""
        if self._running:
            return

        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self):
        """Stop the event dispatcher."""
        self._running = False

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass

    async def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event], Any],
        filter_func: Optional[Callable[[Event], bool]] = None,
        subscriber_id: Optional[str] = None,
    ) -> str:
        """Subscribe to events with optional filtering.

        Args:
            event_type: Type of events to subscribe to
            handler: Async callable to handle events
            filter_func: Optional filter function (return True to process event)
            subscriber_id: Optional subscriber identifier

        Returns:
            Subscriber ID for unsubscribing
        """
        async with self._lock:
            if subscriber_id is None:
                self._subscriber_counter += 1
                subscriber_id = f"subscriber_{self._subscriber_counter}"

            subscriber = Subscriber(
                handler=handler, filter_func=filter_func, subscriber_id=subscriber_id
            )

            self._subscribers[event_type].append(subscriber)
            return subscriber_id

    async def unsubscribe(self, event_type: EventType, subscriber_id: str):
        """Unsubscribe from events.

        Args:
            event_type: Event type to unsubscribe from
            subscriber_id: Subscriber ID returned from subscribe()
        """
        async with self._lock:
            self._subscribers[event_type] = [
                sub
                for sub in self._subscribers[event_type]
                if sub.subscriber_id != subscriber_id
            ]

    async def publish(self, event: Event):
        """Publish event to all subscribers.

        Args:
            event: Event to publish

        Note:
            If queue is full, drops oldest event to prevent blocking (backpressure).
        """
        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            # Backpressure: drop oldest event
            try:
                await self._event_queue.get()
                self._dropped_events_count += 1
            except asyncio.QueueEmpty:
                pass

            # Try again
            try:
                self._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                # Still full, drop this event
                self._dropped_events_count += 1

    def get_stats(self) -> dict:
        """Get event bus statistics."""
        return {
            "queue_size": self._event_queue.qsize(),
            "dropped_events": self._dropped_events_count,
            "subscriber_counts": {
                event_type.value: len(subs)
                for event_type, subs in self._subscribers.items()
            },
        }

    async def _dispatch_loop(self):
        """Background task to dispatch events to subscribers."""
        while self._running:
            try:
                # Wait for next event
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)

                # Get subscribers for this event type
                subscribers = self._subscribers.get(event.type, [])

                # Dispatch to all subscribers
                for subscriber in subscribers:
                    # Check filter
                    if subscriber.filter_func is not None:
                        try:
                            if not subscriber.filter_func(event):
                                continue
                        except Exception:
                            # Filter error - skip this subscriber
                            continue

                    # Call handler
                    try:
                        # Handle both sync and async handlers
                        if asyncio.iscoroutinefunction(subscriber.handler):
                            await subscriber.handler(event)
                        else:
                            subscriber.handler(event)
                    except Exception:
                        # Handler error - continue to other subscribers
                        # Errors are logged at a higher level
                        continue

            except asyncio.TimeoutError:
                # No event available, continue waiting
                continue

            except asyncio.CancelledError:
                # Dispatcher stopped
                break

            except Exception:
                # Unexpected error in dispatch loop - continue running
                continue


# Convenience functions for sensor events
def create_sensor_event(sensor_name: str, data: dict, source: str = "sensor_manager") -> Event:
    """Create a sensor data event.

    Args:
        sensor_name: Name of sensor (e.g., 'accelerometer')
        data: Sensor reading data
        source: Source of the event

    Returns:
        Sensor event
    """
    return Event(
        type=EventType.SENSOR_DATA,
        data={"sensor": sensor_name, "reading": data},
        source=source,
    )


def create_connection_event(state: str, details: dict) -> Event:
    """Create a connection state change event.

    Args:
        state: New connection state
        details: Additional connection details

    Returns:
        Connection event
    """
    return Event(
        type=EventType.CONNECTION_STATE,
        data={"state": state, "details": details},
        source="connection_manager",
    )


def create_safety_event(event_type: str, data: dict) -> Event:
    """Create a safety system event.

    Args:
        event_type: Type of safety event (e.g., 'emergency_stop', 'speed_limit_applied')
        data: Event data

    Returns:
        Safety event
    """
    return Event(
        type=EventType.SAFETY_EVENT,
        data={"event_type": event_type, **data},
        source="safety_monitor",
    )
