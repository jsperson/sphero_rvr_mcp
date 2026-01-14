# Sphero RVR MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that enables AI assistants to control a [Sphero RVR](https://sphero.com/collections/rvr) robot. Run this on a Raspberry Pi connected to your RVR, and use any MCP-compatible client to drive, control LEDs, read sensors, and more.

## Features

### Core Capabilities
- **Full RVR Control**: Movement, LEDs, sensors, battery monitoring, IR communication
- **Safety System**: Configurable speed limits, auto-stop timeout, emergency stop
- **Sensor Streaming**: Background streaming with cached data access
- **Natural Language Control**: Let AI drive your robot with conversational commands
- **Client Agnostic**: Works with any MCP-compatible client

### Production-Grade Architecture (v0.2.0+)
- **Command Queue**: Priority-based async queue eliminates race conditions
- **Circuit Breaker**: Prevents infinite hangs when RVR is powered off
- **Event Bus**: Pub/sub pattern for efficient sensor data distribution
- **Atomic State Management**: Thread-safe state with validated transitions
- **Comprehensive Observability**: Structured logging (JSON/console) + Prometheus metrics
- **No Hard-Coded Delays**: Event-driven connection (no 2-second sleep on connect)
- **Robust Error Handling**: No silent failures, all errors logged and reported

## Compatible MCP Clients

- [Claude Code](https://claude.com/claude-code) (CLI)
- [Claude Desktop](https://claude.ai/download)
- [Cursor](https://cursor.sh/)
- [Zed](https://zed.dev/)
- [Continue.dev](https://continue.dev/)
- Any custom client using the [MCP SDK](https://modelcontextprotocol.io/sdks)

## Requirements

- Raspberry Pi 3 or newer (connected to Sphero RVR via serial)
- Python 3.10+ (3.10.x recommended for Sphero SDK compatibility)
- Sphero RVR with serial connection to Pi
- An MCP-compatible client

## Installation

### 1. Clone the Sphero SDK

The Sphero SDK is not available on PyPI and must be installed manually:

```bash
cd ~
git clone https://github.com/sphero-inc/sphero-sdk-raspberrypi-python.git
```

### 2. Install the MCP Server

**Option A: Install from PyPI** (recommended)

```bash
pip install sphero-rvr-mcp

# Add Sphero SDK to Python path (add to ~/.bashrc for persistence)
export PYTHONPATH="${PYTHONPATH}:${HOME}/sphero-sdk-raspberrypi-python"
```

**Option B: Install from source**

```bash
git clone https://github.com/jsperson/sphero_rvr_mcp.git
cd sphero_rvr_mcp

# Install the package in development mode
pip install -e .

# Add Sphero SDK to Python path (add to ~/.bashrc for persistence)
export PYTHONPATH="${PYTHONPATH}:${HOME}/sphero-sdk-raspberrypi-python"
```

### 3. Verify Installation

Run the pre-flight check to verify everything is set up correctly:

```bash
sphero-rvr-mcp --check
```

This will verify:
- Python version (requires 3.10+)
- Sphero SDK is installed
- FastMCP is installed
- Serial port exists and is accessible
- Current configuration settings

### 4. Configure Your MCP Client

The server runs via stdio. Configure your MCP client with:

- **Command**: `python -m sphero_rvr_mcp`
- **Environment**: `PYTHONPATH` must include the Sphero SDK path

#### Claude Code

```bash
claude mcp add sphero-rvr -c "python -m sphero_rvr_mcp"
```

Or edit `~/.claude.json`:

```json
{
  "mcpServers": {
    "sphero-rvr": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "sphero_rvr_mcp"],
      "env": {
        "PYTHONPATH": "<your-home-dir>/sphero-sdk-raspberrypi-python"
      }
    }
  }
}
```

#### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "sphero-rvr": {
      "command": "python",
      "args": ["-m", "sphero_rvr_mcp"],
      "env": {
        "PYTHONPATH": "<path-to>/sphero-sdk-raspberrypi-python"
      }
    }
  }
}
```

#### Other Clients

Refer to your client's MCP configuration documentation. The server uses stdio transport.

## Configuration

Environment variables (optional):

| Variable | Default | Description |
|----------|---------|-------------|
| **Connection** | | |
| `RVR_SERIAL_PORT` | `/dev/ttyS0` | Serial port for RVR |
| `RVR_BAUD_RATE` | `115200` | Serial baud rate |
| `RVR_WAKE_TIMEOUT` | `5.0` | RVR wake timeout (seconds) |
| **Safety** | | |
| `RVR_MAX_SPEED_PERCENT` | `50.0` | Default speed limit (0-100) |
| `RVR_COMMAND_TIMEOUT` | `5.0` | Auto-stop timeout (seconds, 0=disabled) |
| **Performance** | | |
| `RVR_COMMAND_QUEUE_SIZE` | `100` | Max queued commands |
| `RVR_SENSOR_CACHE_TTL` | `2.0` | Sensor data TTL (seconds) |
| **Observability** | | |
| `RVR_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `RVR_LOG_FORMAT` | `json` | Log format (json, console) |
| `RVR_METRICS_ENABLED` | `true` | Enable Prometheus metrics |
| `RVR_METRICS_PORT` | `9090` | Metrics HTTP server port |
| **Circuit Breaker** | | |
| `RVR_CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Failures before opening |
| `RVR_CIRCUIT_BREAKER_TIMEOUT` | `30.0` | Timeout before half-open (seconds) |

## Usage

### Example Commands

Once your MCP client is connected to the server:

```
You: Connect to the RVR

You: Drive forward slowly for 2 seconds then stop

You: Set all LEDs to blue

You: What's the battery level?

You: Start streaming the accelerometer and gyroscope sensors

You: Turn left 90 degrees

You: What color is under the rover?

You: Emergency stop!
```

## Available Tools

### Connection (3 tools)
| Tool | Description |
|------|-------------|
| `connect` | Connect to RVR and wake it up |
| `disconnect` | Safely disconnect |
| `get_connection_status` | Get connection state, uptime, firmware |

### Movement (9 tools)
| Tool | Description |
|------|-------------|
| `drive_with_heading` | Drive at speed toward heading (0-359°) |
| `drive_tank` | Tank drive with left/right velocities (m/s) |
| `drive_rc` | RC-style with linear + yaw velocity |
| `stop` | Normal stop |
| `emergency_stop` | Immediate stop, blocks movement |
| `clear_emergency_stop` | Allow movement after e-stop |
| `reset_yaw` | Set current heading as 0° |
| `reset_locator` | Set current position as origin |

### LEDs (3 tools)
| Tool | Description |
|------|-------------|
| `set_all_leds` | Set all LEDs to RGB color |
| `set_led` | Set specific LED group to RGB |
| `turn_leds_off` | Turn off all LEDs |

LED groups: `headlight_left`, `headlight_right`, `brakelight_left`, `brakelight_right`, `status_indication_left`, `status_indication_right`, `battery_door_front`, `battery_door_rear`, `power_button_front`, `power_button_rear`, `undercarriage_white`, `all`

### Sensors (6 tools)
| Tool | Description |
|------|-------------|
| `start_sensor_streaming` | Start background sensor streaming |
| `stop_sensor_streaming` | Stop all streaming |
| `get_sensor_data` | Get cached sensor readings |
| `get_ambient_light` | Query light sensor directly |
| `enable_color_detection` | Enable/disable color sensor LED |
| `get_color_detection` | Query color sensor (auto LED) |

Streamable sensors: `accelerometer`, `gyroscope`, `imu`, `locator`, `velocity`, `speed`, `quaternion`, `color_detection`, `ambient_light`, `core_time`

### Battery & System (2 tools)
| Tool | Description |
|------|-------------|
| `get_battery_status` | Battery percentage and voltage state |
| `get_system_info` | Connection info and uptime |

### Safety Controls (3 tools)
| Tool | Description |
|------|-------------|
| `get_safety_status` | Current safety settings |
| `set_speed_limit` | Set max speed (0-100%) |
| `set_command_timeout` | Set auto-stop timeout |

### IR Communication (3 tools)
| Tool | Description |
|------|-------------|
| `send_ir_message` | Send IR code (0-7) |
| `start_ir_broadcasting` | Start robot-to-robot IR |
| `stop_ir_broadcasting` | Stop IR broadcasting |

## Architecture

### Component Overview

```
MCP Tool Handlers (FastMCP)
    ↓
Application Services Layer
├── ConnectionService
├── MovementService
├── SensorService
├── LEDService
├── SafetyService
└── IRService
    ↓
Core Infrastructure
├── Command Queue (priority + timeout)
├── Event Bus (pub/sub)
├── Circuit Breaker (resilience)
└── State Manager (atomic)
    ↓
Hardware Abstraction
├── Connection Manager
├── Sensor Stream Manager
└── Safety Monitor
    ↓
Sphero RVR SDK
```

### Key Design Patterns

**Command Queue**
- All hardware commands go through async priority queue
- Priority levels: EMERGENCY (0) → HIGH (1) → NORMAL (2) → LOW (3)
- Per-command timeout enforcement
- Eliminates race conditions in concurrent access

**Circuit Breaker**
- States: CLOSED (healthy) → OPEN (failing) → HALF_OPEN (testing)
- Prevents infinite hangs when RVR is powered off
- Automatic recovery with configurable threshold
- Fails fast when unhealthy

**Event Bus**
- Pub/sub pattern for sensor data distribution
- Decouples streaming from consumers
- Built-in backpressure management
- Multiple subscribers per sensor

**Atomic State Management**
- Thread-safe with explicit locks
- Validated state transitions
- Separate state objects: SystemState, ConnectionInfo, SafetyState, SensorState
- All changes logged and metered

### Observability

**Structured Logging**
```json
{
  "event": "command_submitted",
  "command_type": "drive_with_heading",
  "speed": 50,
  "heading": 90,
  "timestamp": "2026-01-14T01:23:45.678Z"
}
```

**Prometheus Metrics** (port 9090 by default)
- Command metrics: total, duration, queue depth
- Connection metrics: state, reconnections, uptime
- Safety metrics: emergency stops, speed limits applied
- Sensor metrics: streaming active, data age, events
- Circuit breaker metrics: state, failures, successes

## Safety Features

### Speed Limiting
All movement commands are limited to a configurable percentage of max speed (default 50%). This prevents accidental high-speed collisions.

```
You: Set the speed limit to 25%
You: Now drive forward at full speed
# RVR will only go at 25% of max speed
```

### Command Timeout
If no movement command is received within the timeout period (default 5 seconds), the RVR automatically stops. This prevents runaway situations if connection is lost.

### Emergency Stop
Immediately stops all movement and blocks further motion until explicitly cleared. Has highest priority in the command queue.

```
You: Emergency stop!
# RVR stops immediately
# All movement commands will fail until:
You: Clear the emergency stop
```

## Troubleshooting

### Connection Issues

**"Failed to connect to RVR"**
- Check serial connection: `ls -l /dev/ttyS0`
- Ensure RVR is powered on and charged
- Verify baud rate (default 115200)
- Check circuit breaker isn't open (connection status)

**"RVR wake() timed out"**
- RVR might be off or in deep sleep
- Try power cycling the RVR
- Check serial cable connection
- Circuit breaker will open after 5 failures (default)

### SDK Issues

**"sphero_sdk not found"**
- Add SDK to PYTHONPATH: `export PYTHONPATH="${PYTHONPATH}:/path/to/sphero-sdk-raspberrypi-python"`
- Add to `~/.bashrc` for persistence
- Verify SDK is cloned: `ls ~/sphero-sdk-raspberrypi-python`

**"nest_asyncio required"**
- The Sphero SDK requires nested event loops
- This is normal and handled automatically by the server

### Performance Issues

**Slow response**
- Raspberry Pi 3 may be slower than Pi 4/5
- Reduce sensor streaming frequency
- Close unnecessary applications
- Check command queue depth (metrics endpoint)

**Commands timing out**
- Check circuit breaker state (connection status)
- Verify RVR is not in emergency stop
- Increase command timeout in configuration
- Check system logs for errors

### Sensor Issues

**Color detection returns all zeros**
- This is fixed in v0.2.0+ (SDK key parsing)
- Ensure RVR is on a non-dark surface
- Try increasing stabilization time
- Check that belly LED is working

**Sensor streaming not updating**
- Verify streaming is started: `get_sensor_data`
- Check sensor cache TTL (default 2 seconds)
- Verify sensors are in available list
- Check event bus metrics

### RVR Behavior Issues

**RVR not responding to commands**
- Check if emergency stop is active: `get_safety_status`
- Verify connection: `get_connection_status`
- Check speed limit isn't set to 0%
- Try disconnecting and reconnecting

**RVR stops on its own**
- Check command timeout setting (default 5 seconds)
- Disable auto-stop: `set_command_timeout(0)`
- Verify battery level isn't critical

## Metrics & Monitoring

Access Prometheus metrics at `http://<raspberry-pi-ip>:9090/metrics` (if enabled).

**Key Metrics:**
- `rvr_commands_total` - Total commands by type and status
- `rvr_command_duration_seconds` - Command latency histogram
- `rvr_command_queue_depth` - Current queue depth
- `rvr_connection_state` - Connection state (0=disconnected, 1=connecting, 2=connected, 3=error)
- `rvr_emergency_stops_total` - Emergency stop count
- `rvr_sensor_streaming_active` - Sensor streaming status
- `rvr_circuit_breaker_state` - Circuit breaker state (0=closed, 1=open, 2=half_open)

## Project Structure

```
sphero_rvr_mcp/
├── pyproject.toml              # Package configuration
├── README.md                   # This file
├── LICENSE                     # MIT License
└── src/sphero_rvr_mcp/
    ├── __init__.py
    ├── __main__.py             # Entry point
    ├── config.py               # Configuration
    ├── api.py                  # Direct API (non-MCP)
    ├── server.py               # MCP server
    │
    ├── core/                   # Core infrastructure
    │   ├── command_queue.py    # Priority command queue
    │   ├── circuit_breaker.py  # Circuit breaker pattern
    │   ├── event_bus.py        # Pub/sub event bus
    │   ├── state_manager.py    # Atomic state management
    │   └── exceptions.py       # Exception hierarchy
    │
    ├── hardware/               # Hardware abstraction
    │   ├── connection_manager.py       # Connection lifecycle
    │   ├── sensor_stream_manager.py    # Sensor streaming
    │   └── safety_monitor.py           # Safety system
    │
    ├── services/               # Application services
    │   ├── connection_service.py
    │   ├── movement_service.py
    │   ├── sensor_service.py
    │   ├── led_service.py
    │   ├── safety_service.py
    │   └── ir_service.py
    │
    ├── tools/                  # MCP tool handlers
    │   ├── connection_tools.py
    │   ├── movement_tools.py
    │   ├── sensor_tools.py
    │   ├── led_tools.py
    │   ├── safety_tools.py
    │   └── ir_tools.py
    │
    └── observability/          # Logging & metrics
        ├── logging.py          # Structured logging
        ├── metrics.py          # Prometheus metrics
        └── health.py           # Health monitoring
```

## Direct API Usage (Non-MCP)

You can also use the RVR client directly without MCP:

```python
import asyncio
from sphero_rvr_mcp.api import RVRClient

async def main():
    client = RVRClient(log_level="INFO", log_format="console")

    await client.initialize()
    await client.connect()

    # Control LEDs
    await client.set_all_leds(255, 0, 0)  # Red

    # Read sensors
    color = await client.get_color_detection()
    print(f"Color: {color}")

    # Movement (if not wired up!)
    # await client.drive_with_heading(speed=50, heading=0)

    await client.shutdown()

asyncio.run(main())
```

## Development

### Running Tests

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires RVR)
pytest tests/integration/

# All tests
pytest
```

### Viewing Logs

```bash
# Console format (human-readable)
RVR_LOG_FORMAT=console python -m sphero_rvr_mcp

# JSON format (machine-readable)
RVR_LOG_FORMAT=json python -m sphero_rvr_mcp
```

### Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Changelog

### v0.2.0 (2026-01-14)
- **Complete architectural rewrite** for production reliability
- Added command queue with priority levels
- Added circuit breaker for connection resilience
- Added event bus for sensor distribution
- Added atomic state management
- Added comprehensive observability (logging + metrics)
- Fixed SDK response key parsing (color sensor now works!)
- Removed hard-coded delays (2s sleep eliminated)
- Enhanced battery status with voltage state
- Improved error handling (no silent failures)

### v0.1.1 (2024-12-XX)
- Added connection timeouts
- Updated documentation

### v0.1.0 (2024-12-XX)
- Initial release

## License

MIT

## Credits

- [Sphero RVR SDK](https://github.com/sphero-inc/sphero-sdk-raspberrypi-python)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [Model Context Protocol](https://modelcontextprotocol.io/)
