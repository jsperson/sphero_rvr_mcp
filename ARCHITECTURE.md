# Architecture Documentation

## Overview

The Sphero RVR MCP Server uses a production-grade layered architecture with robust error handling, comprehensive observability, and modern async patterns.

## Design Principles

1. **Separation of Concerns**: Clear boundaries between MCP tools, application services, infrastructure, and hardware
2. **Fail-Safe**: No silent failures - all errors logged and reported
3. **Resilience**: Circuit breaker prevents cascading failures
4. **Concurrency Safety**: Command queue eliminates race conditions
5. **Observability**: Structured logging and Prometheus metrics throughout
6. **Performance**: Event-driven, no hard-coded delays

## Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client (Claude)                       │
└───────────────────────┬─────────────────────────────────────┘
                        │ stdio
┌───────────────────────▼─────────────────────────────────────┐
│              FastMCP Server (server.py)                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              MCP Tool Handlers                       │   │
│  │  connection_tools │ movement_tools │ sensor_tools    │   │
│  │  led_tools │ safety_tools │ ir_tools                 │   │
│  └───────────────┬──────────────────────────────────────┘   │
└──────────────────┼──────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────┐
│            Application Services Layer                        │
│  ┌────────────┬─────────────┬──────────────┬────────────┐   │
│  │Connection  │ Movement    │ Sensor       │ LED        │   │
│  │Service     │ Service     │ Service      │ Service    │   │
│  ├────────────┴─────────────┴──────────────┴────────────┤   │
│  │ Safety Service          │ IR Service                 │   │
│  └──────────┬──────────────┴────────────────────────────┘   │
└─────────────┼───────────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────────────┐
│              Core Infrastructure                             │
│  ┌────────────────┬─────────────┬────────────────────────┐  │
│  │ Command Queue  │ Event Bus   │ Circuit Breaker        │  │
│  │ (Priority)     │ (Pub/Sub)   │ (Resilience)           │  │
│  ├────────────────┴─────────────┴────────────────────────┤  │
│  │          State Manager (Atomic)                       │  │
│  └───────────────────┬───────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│            Hardware Abstraction Layer                        │
│  ┌────────────────┬──────────────┬─────────────────────┐    │
│  │ Connection     │ Sensor       │ Safety              │    │
│  │ Manager        │ Stream Mgr   │ Monitor             │    │
│  └────────────┬───┴──────────────┴─────────────────────┘    │
└───────────────┼──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│                  Sphero RVR SDK                               │
│              (sphero-sdk-raspberrypi-python)                  │
└───────────────────────────────────────────────────────────────┘
```

## Layer Responsibilities

### MCP Tool Handlers (`tools/`)

**Responsibility**: Thin wrappers that validate MCP inputs and delegate to services

**Key Files**:
- `connection_tools.py` - Connect, disconnect, status
- `movement_tools.py` - Drive, stop, reset
- `sensor_tools.py` - Streaming, queries
- `led_tools.py` - LED control
- `safety_tools.py` - Speed limits, emergency stop
- `ir_tools.py` - IR communication

**Design**:
```python
@mcp.tool()
async def drive_with_heading(speed: int, heading: int) -> dict:
    """Tool docstring exposed to MCP client."""
    # 1. Input validation (Pydantic handles most)
    # 2. Delegate to service
    return await movement_service.drive_with_heading(speed, heading)
```

### Application Services (`services/`)

**Responsibility**: Business logic, service orchestration, error handling

**Key Files**:
- `connection_service.py` - Connection lifecycle
- `movement_service.py` - Movement commands with safety checks
- `sensor_service.py` - Sensor operations
- `led_service.py` - LED operations
- `safety_service.py` - Safety system
- `ir_service.py` - IR communication

**Design**:
```python
class MovementService:
    async def drive_with_heading(self, speed, heading):
        # 1. Ensure connected
        await self._connection_manager.ensure_connected()

        # 2. Check safety
        await self._safety_monitor.check_emergency_stop()

        # 3. Apply speed limiting
        limited_speed, was_limited = await self._safety_monitor.limit_speed(speed)

        # 4. Submit to command queue
        await self._command_queue.submit(command, priority, timeout)

        # 5. Record command for timeout
        await self._safety_monitor.on_movement_command()

        # 6. Return result with metrics
        return {"success": True, "speed": limited_speed}
```

### Core Infrastructure (`core/`)

**Responsibility**: Reusable infrastructure components

#### Command Queue (`command_queue.py`)

**Purpose**: Serialize hardware access, eliminate race conditions

**Design**:
```python
class CommandPriority(IntEnum):
    EMERGENCY = 0  # Emergency stop
    HIGH = 1       # Safety-critical
    NORMAL = 2     # Movement commands
    LOW = 3        # LED, sensor queries

class CommandQueue:
    async def submit(self, command_fn, priority, timeout):
        # 1. Check queue capacity (backpressure)
        # 2. Create command with priority
        # 3. Put in priority queue
        # 4. Wait for execution with timeout
        # 5. Return result
```

**Key Features**:
- Priority-based execution
- Per-command timeout enforcement
- Backpressure (rejects when full)
- Metrics: queue depth, execution time

#### Circuit Breaker (`circuit_breaker.py`)

**Purpose**: Prevent infinite hangs when RVR is offline

**States**:
```
CLOSED (healthy)
   │
   │ Threshold failures reached
   ▼
OPEN (failing) ────────┐
   │                   │
   │ Timeout elapsed   │ Request (fail fast)
   ▼                   │
HALF_OPEN (testing) ◄──┘
   │
   │ Success threshold reached
   ▼
CLOSED (recovered)
```

**Configuration**:
- `failure_threshold`: 5 failures → OPEN
- `timeout_duration`: 30s before HALF_OPEN
- `success_threshold`: 2 successes → CLOSED

**Usage**:
```python
async def wake_operation():
    await self._rvr.wake()

await circuit_breaker.call(wake_operation, timeout=5.0)
```

#### Event Bus (`event_bus.py`)

**Purpose**: Decouple sensor streaming from consumers

**Design**:
```python
class EventBus:
    async def publish(self, event: Event):
        # 1. Add to queue
        # 2. If full, drop oldest (backpressure)
        # 3. Notify subscribers

    async def subscribe(self, pattern: str, handler):
        # Pattern-based subscription (e.g., "sensor.*")
```

**Benefits**:
- Multiple consumers per sensor
- Built-in backpressure
- Filtering support
- Async distribution

#### State Manager (`state_manager.py`)

**Purpose**: Thread-safe atomic state management

**Components**:
```python
class StateManager:
    system_state: SystemState          # Connection, state transitions
    connection_info: ConnectionInfo    # Firmware, MAC, port
    safety_state: SafetyState          # E-stop, limits, timeout
    sensor_state: SensorState          # Streaming, cache
```

**Design**:
```python
class SystemState:
    async def transition_connection_state(self, new_state):
        async with self._lock:
            # 1. Validate transition
            if not self._is_valid_transition(self._state, new_state):
                raise StateTransitionError()

            # 2. Update state
            old_state = self._state
            self._state = new_state

            # 3. Log and meter
            log_state_transition(logger, old_state, new_state)
            metrics.update_connection_state(new_state)
```

### Hardware Abstraction (`hardware/`)

**Responsibility**: Direct SDK interaction, hardware abstraction

#### Connection Manager (`connection_manager.py`)

**Purpose**: RVR connection lifecycle

**Key Features**:
- Event-driven readiness check (no hard-coded sleep)
- Circuit breaker integration
- Atomic state transitions
- Graceful firmware/MAC queries (non-blocking)

**Connection Flow**:
```python
1. Validate state (must be DISCONNECTED)
2. Transition to CONNECTING
3. Create SerialAsyncDal with event loop
4. Create RVR SDK instance
5. Wake RVR through circuit breaker
6. Poll for readiness (battery query, not sleep!)
7. Query firmware/MAC (graceful fallback to "unknown")
8. Transition to CONNECTED
9. Initialize services
```

#### Sensor Stream Manager (`sensor_stream_manager.py`)

**Purpose**: Efficient sensor streaming

**Key Features**:
- Pre-built service map (O(1) lookup, no `dir()` loop)
- Event bus integration
- Thread-safe caching with TTL
- Direct queries (ambient light, color, battery)

**Streaming Flow**:
```python
1. Map sensor names to RvrStreamingServices (O(1))
2. Create handler that publishes to event bus
3. Register with SDK
4. Start streaming at interval
5. Handlers update cache + publish events
```

#### Safety Monitor (`safety_monitor.py`)

**Purpose**: Atomic safety operations

**Key Features**:
- Atomic emergency stop flag (no races)
- Speed limiting (0-255 and m/s)
- Command timeout with task management

**Speed Limiting**:
```python
async def limit_speed(self, speed: int) -> tuple[int, bool]:
    limit_percent = await self.get_speed_limit()
    max_speed = int(255 * limit_percent / 100.0)
    limited_speed = min(speed, max_speed)
    was_limited = limited_speed < speed

    if was_limited:
        metrics.record_speed_limit_applied()
        log_safety_event(logger, "speed_limited", ...)

    return limited_speed, was_limited
```

### Observability (`observability/`)

**Responsibility**: Logging, metrics, health monitoring

#### Structured Logging (`logging.py`)

**Setup**:
```python
configure_logging(
    log_level="INFO",
    log_format="json",  # or "console"
    add_logger_name=True,
    add_thread_info=False
)
```

**JSON Output**:
```json
{
  "event": "command_submitted",
  "command_type": "drive_with_heading",
  "speed": 50,
  "heading": 90,
  "timestamp": "2026-01-14T01:23:45.678Z",
  "level": "info",
  "logger": "sphero_rvr_mcp.services.movement_service"
}
```

**Convenience Functions**:
```python
log_command_submitted(logger, "drive_with_heading", speed=50)
log_command_completed(logger, "drive_with_heading", duration_ms=25.3)
log_state_transition(logger, "disconnected", "connecting")
log_safety_event(logger, "emergency_stop_activated")
```

#### Prometheus Metrics (`metrics.py`)

**Command Metrics**:
- `rvr_commands_total{command_type, status}` - Counter
- `rvr_command_duration_seconds{command_type}` - Histogram
- `rvr_command_queue_depth` - Gauge

**Connection Metrics**:
- `rvr_connection_state` - Enum (disconnected=0, connecting=1, connected=2, error=3)
- `rvr_connection_attempts_total{result}` - Counter
- `rvr_connection_uptime_seconds` - Gauge

**Safety Metrics**:
- `rvr_emergency_stops_total` - Counter
- `rvr_speed_limits_applied_total` - Counter
- `rvr_speed_limit_percent` - Gauge

**Sensor Metrics**:
- `rvr_sensor_streaming_active` - Gauge
- `rvr_sensor_events_total{sensor}` - Counter
- `rvr_sensor_data_age_seconds` - Histogram

**Circuit Breaker Metrics**:
- `rvr_circuit_breaker_state` - Enum (closed=0, open=1, half_open=2)
- `rvr_circuit_breaker_failures_total` - Counter
- `rvr_circuit_breaker_successes_total` - Counter

## Data Flow Examples

### Movement Command

```
User: "Drive forward at 50"
  │
  ▼
MCP Tool: drive_with_heading(speed=50, heading=0)
  │
  ▼
MovementService.drive_with_heading()
  │
  ├─► ConnectionManager.ensure_connected()
  ├─► SafetyMonitor.check_emergency_stop()
  ├─► SafetyMonitor.limit_speed(50) → 25 (if limit is 50%)
  │
  ▼
CommandQueue.submit(command, NORMAL, timeout=1.0)
  │
  ├─► Queue: [EMERGENCY, HIGH, NORMAL*, LOW]
  │
  ▼
Execute: rvr.drive_with_heading(speed=25, heading=0, flags=0)
  │
  ▼
SafetyMonitor.on_movement_command()
  │
  ├─► Cancel old timeout task
  ├─► Create new timeout task (auto-stop in 5s)
  │
  ▼
Return: {"success": true, "speed": 25, "was_limited": true}
  │
  ▼
MCP Response to Claude
```

### Sensor Streaming

```
User: "Start streaming accelerometer"
  │
  ▼
MCP Tool: start_sensor_streaming(["accelerometer"], 250)
  │
  ▼
SensorService.start_sensor_streaming()
  │
  ▼
SensorStreamManager.start_streaming()
  │
  ├─► Map "accelerometer" → RvrStreamingServices.accelerometer
  ├─► Create handler:
  │     async def handler(data):
  │       await state_manager.sensor_state.update_cache(sensor, data)
  │       await event_bus.publish(SensorEvent(sensor, data))
  │
  ├─► SDK: add_sensor_data_handler(service, handler)
  ├─► SDK: sensor_control.start(interval=250)
  │
  ▼
Background: RVR → SDK → handler → EventBus → Subscribers
                                 └─► StateManager (cache)
```

### Emergency Stop

```
User: "Emergency stop!"
  │
  ▼
MCP Tool: emergency_stop()
  │
  ▼
MovementService.emergency_stop()
  │
  ▼
SafetyMonitor.emergency_stop()
  │
  ├─► StateManager.safety_state.set_emergency_stop(True)  [ATOMIC]
  ├─► metrics.record_emergency_stop()
  ├─► EventBus.publish(SafetyEvent("emergency_stop", {active: true}))
  │
  ▼
CommandQueue.submit(stop_command, EMERGENCY, timeout=0.5)
  │
  ├─► Queue: [EMERGENCY*, HIGH, NORMAL, LOW]
  ├─► Jumps to front of queue
  │
  ▼
Execute: rvr.drive_stop()
  │
  ▼
Cancel timeout task
  │
  ▼
Return: {"success": true, "message": "Emergency stop activated"}
  │
  ▼
All subsequent movement commands will fail with:
SafetyError("Emergency stop is active. Clear it before issuing commands.")
```

## Error Handling Strategy

### Exception Hierarchy

```python
RVRError (base)
├── ConnectionError
├── CommandError
│   ├── CommandTimeoutError
│   └── CommandQueueFullError
├── SensorError
├── SafetyError
└── CircuitBreakerOpenError
```

### No Silent Failures

**Before (v0.1.x)**:
```python
try:
    await operation()
except Exception:
    pass  # SILENT FAILURE ❌
```

**After (v0.2.0)**:
```python
try:
    await operation()
except SpecificError as e:
    logger.error("operation_failed", error=str(e))
    metrics.operation_failures.inc()
    return {"success": False, "error": str(e)}
```

### Error Propagation

1. **Hardware Layer**: Raises specific exceptions
2. **Service Layer**: Catches, logs, meters, returns error dicts
3. **Tool Layer**: Returns error dicts to MCP client
4. **Client**: Sees human-readable error messages

## Performance Optimizations

### Removed Hard-Coded Delays

**Before**:
```python
await self._rvr.wake()
await asyncio.sleep(2)  # ❌ Always 2 seconds
```

**After**:
```python
await self._rvr.wake()
await self._wait_for_ready(timeout=5.0)  # ✅ Event-driven

async def _wait_for_ready(self, timeout):
    start = time.time()
    while time.time() - start < timeout:
        try:
            await asyncio.wait_for(
                self._rvr.get_battery_percentage(),
                timeout=0.5
            )
            return  # Ready!
        except:
            await asyncio.sleep(0.1)  # Short poll
```

### Optimized Sensor Registration

**Before**:
```python
# O(n) loop through all attributes
for attr in dir(RvrStreamingServices):
    if not attr.startswith('_'):
        # ...
```

**After**:
```python
# O(1) lookup
SENSOR_SERVICE_MAP = {
    'accelerometer': RvrStreamingServices.accelerometer,
    'gyroscope': RvrStreamingServices.gyroscope,
    # ...pre-built
}

service = SENSOR_SERVICE_MAP.get(sensor_name)
```

### Adaptive Timeouts

Different command types have different timeout requirements:

```python
WAKE_TIMEOUT = 5.0
SENSOR_QUERY_TIMEOUT = 2.0
MOVEMENT_COMMAND_TIMEOUT = 1.0
LED_COMMAND_TIMEOUT = 0.5
EMERGENCY_STOP_TIMEOUT = 0.5
```

## Configuration Management

### Environment Variables

Loaded via `config.py`:

```python
@dataclass
class RVRConfig:
    serial_port: str = os.getenv("RVR_SERIAL_PORT", "/dev/ttyS0")
    baud_rate: int = int(os.getenv("RVR_BAUD_RATE", "115200"))
    max_speed_percent: float = float(os.getenv("RVR_MAX_SPEED_PERCENT", "50.0"))
    # ...
```

### Defaults Hierarchy

1. Environment variables (highest precedence)
2. Config file (if supported)
3. Code defaults (fallback)

## Testing Strategy

### Unit Tests

Test individual components in isolation:

```python
async def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

    # Cause 3 failures
    for _ in range(3):
        with pytest.raises(Exception):
            await breaker.call(failing_operation)

    # Should now be OPEN
    assert breaker.state == CircuitState.OPEN
```

### Integration Tests

Test component interactions with real RVR:

```python
async def test_color_detection_integration():
    client = RVRClient()
    await client.initialize()
    await client.connect()

    result = await client.get_color_detection()

    assert result["success"]
    assert "r" in result
    assert "g" in result
    assert "b" in result
    assert "c" in result
```

### Mocking

Use mock RVR adapter for tests without hardware:

```python
class MockRVRAdapter:
    def __init__(self, failure_rate=0.0, latency_ms=10.0):
        self._failure_rate = failure_rate
        self._latency_ms = latency_ms

    async def wake(self):
        await asyncio.sleep(self._latency_ms / 1000.0)
        if random.random() < self._failure_rate:
            raise ConnectionError("Mock failure")
```

## Deployment Considerations

### Resource Requirements

- **CPU**: Low (async I/O bound)
- **Memory**: ~50MB baseline
- **Network**: None (serial only)
- **Storage**: Minimal (logs)

### Monitoring

1. **Prometheus Metrics**: Export on port 9090
2. **Structured Logs**: JSON format to stdout
3. **Health Checks**: Connection status, circuit breaker state

### Scaling

Single RVR = single instance (serial connection is exclusive).

For multiple RVRs:
- Run separate instances on different ports
- Different MCP server names
- Different Prometheus metrics ports

## Future Enhancements

### Planned

- [ ] WebSocket transport (in addition to stdio)
- [ ] Replay buffer for debugging
- [ ] Trajectory planning
- [ ] Obstacle avoidance
- [ ] Multi-RVR coordination

### Under Consideration

- [ ] GraphQL API
- [ ] REST API alongside MCP
- [ ] Video streaming integration
- [ ] Machine learning integration

## References

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [Sphero RVR SDK](https://github.com/sphero-inc/sphero-sdk-raspberrypi-python)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
