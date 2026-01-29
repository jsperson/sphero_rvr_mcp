# Sphero RVR MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that enables AI assistants to control a [Sphero RVR](https://sphero.com/collections/rvr) robot. Run this on a Raspberry Pi connected to your RVR, and use any MCP-compatible client to drive, control LEDs, read sensors, and more.

## Features

### Core Capabilities
- **Full RVR Control**: Movement, LEDs, sensors, battery monitoring, IR communication
- **Distance-Based Movement**: Drive forward/backward by meters, pivot by degrees
- **Safety System**: Configurable speed limits, auto-stop timeout, emergency stop
- **Sensor Streaming**: Background streaming with cached data access
- **Natural Language Control**: Let AI drive your robot with conversational commands
- **Client Agnostic**: Works with any MCP-compatible client

### Low-Latency Architecture (v0.2.1+)
- **Direct Serial Protocol**: Bypasses SDK for sub-millisecond command latency
- **No Sphero SDK Required**: Works on Python 3.10 - 3.13+ (SDK was limited to 3.10)
- **Minimal Dependencies**: Just 4 packages (fastmcp, pydantic, structlog, pyserial)
- **Distance Control**: `drive_forward(0.5)` moves exactly 0.5 meters
- **Angle Control**: `pivot(90)` rotates exactly 90 degrees
- **Command Queue**: Priority-based async queue eliminates race conditions
- **Atomic State Management**: Thread-safe state with validated transitions
- **Structured Logging**: JSON or console format for easy debugging

## Compatible MCP Clients

- [Claude Code](https://claude.com/claude-code) (CLI)
- [Claude Desktop](https://claude.ai/download)
- [Cursor](https://cursor.sh/)
- [Zed](https://zed.dev/)
- [Continue.dev](https://continue.dev/)
- Any custom client using the [MCP SDK](https://modelcontextprotocol.io/sdks)

## Requirements

- Raspberry Pi 3 or newer (connected to Sphero RVR via serial)
- Python 3.10+ (tested on 3.10, 3.12, 3.13 - no SDK limitations)
- Sphero RVR with serial connection to Pi

## Installation

### Install from PyPI (recommended)

```bash
pip install sphero-rvr-mcp
```

### Install from source

```bash
git clone https://github.com/jsperson/sphero_rvr_mcp.git
cd sphero_rvr_mcp
pip install -e .
```

### Verify Installation

Run the pre-flight check to verify everything is set up correctly:

```bash
sphero-rvr-mcp --check
```

This will verify:
- Python version (requires 3.10+)
- FastMCP is installed
- Serial port exists and is accessible
- Current configuration settings

### Configure Your MCP Client

The server runs via stdio. Configure your MCP client with:

- **Command**: `python -m sphero_rvr_mcp`

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
      "args": ["-m", "sphero_rvr_mcp"]
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
      "args": ["-m", "sphero_rvr_mcp"]
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
| `RVR_SERIAL_PORT` | `/dev/ttyAMA0` | Serial port for RVR |
| `RVR_BAUD_RATE` | `115200` | Serial baud rate |
| **Safety** | | |
| `RVR_MAX_SPEED_PERCENT` | `50.0` | Default speed limit (0-100) |
| `RVR_COMMAND_TIMEOUT` | `5.0` | Auto-stop timeout (seconds, 0=disabled) |
| **Performance** | | |
| `RVR_COMMAND_QUEUE_SIZE` | `100` | Max queued commands |
| **Observability** | | |
| `RVR_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `RVR_LOG_FORMAT` | `json` | Log format (json, console) |

## Usage

### Example Commands

Once your MCP client is connected to the server:

```
You: Connect to the RVR

You: Drive forward 6 inches

You: Pivot 90 degrees to the right

You: Drive forward 1 meter

You: Set all LEDs to blue

You: What's the battery level?

You: Which direction is the rover facing?
# Returns heading in degrees and cardinal direction (N, NE, E, SE, S, SW, W, NW)

You: Turn left 45 degrees and drive backward 0.5 meters

You: Emergency stop!
```

## Available Tools

### Connection (3 tools)
| Tool | Description |
|------|-------------|
| `connect` | Connect to RVR and wake it up |
| `disconnect` | Safely disconnect |
| `get_connection_status` | Get connection state, uptime, firmware |

### Movement (11 tools)
| Tool | Description |
|------|-------------|
| `drive_forward` | Drive forward by distance in meters |
| `drive_backward` | Drive backward by distance in meters |
| `pivot` | Turn in place by degrees (positive=right, negative=left) |
| `drive_with_heading` | Drive at speed toward heading (0-359) |
| `drive_tank` | Tank drive with left/right velocities (m/s) |
| `drive_rc` | RC-style with linear + yaw velocity |
| `stop` | Normal stop |
| `emergency_stop` | Immediate stop, blocks movement |
| `clear_emergency_stop` | Allow movement after e-stop |
| `reset_yaw` | Set current heading as 0 |
| `reset_locator` | Set current position as origin |

### LEDs (3 tools)
| Tool | Description |
|------|-------------|
| `set_all_leds` | Set all LEDs to RGB color |
| `set_led` | Set specific LED group to RGB |
| `turn_leds_off` | Turn off all LEDs |

LED groups: `headlight_left`, `headlight_right`, `brakelight_left`, `brakelight_right`, `status_indication_left`, `status_indication_right`, `battery_door_front`, `battery_door_rear`, `power_button_front`, `power_button_rear`, `undercarriage_white`, `all`

### Sensors (12 tools)
| Tool | Description |
|------|-------------|
| `start_sensor_streaming` | Start background sensor streaming |
| `stop_sensor_streaming` | Stop all streaming |
| `get_sensor_data` | Get cached sensor readings |
| `get_ambient_light` | Query light sensor directly |
| `enable_color_detection` | Enable/disable color sensor LED |
| `get_color_detection` | Query color sensor (auto LED) |
| `get_magnetometer` | Get compass heading and cardinal direction |
| `calibrate_magnetometer` | Calibrate compass (rotate 360°) |
| `get_temperature` | Get motor temperatures (°C) |
| `get_encoder_counts` | Get wheel encoder tick counts |
| `get_motor_thermal_protection_status` | Motor thermal state (ok/warning/critical) |
| `get_ir_readings` | Get IR sensor readings (bot-to-bot, 255=no signal) |

Streamable sensors: `accelerometer`, `gyroscope`, `imu`, `locator`, `velocity`, `speed`, `quaternion`, `color_detection`, `ambient_light`, `core_time`

### Battery & System (11 tools)
| Tool | Description |
|------|-------------|
| `get_battery_status` | Battery percentage |
| `get_battery_voltage` | Battery voltage in volts |
| `get_battery_voltage_state` | Battery state (ok/low/critical) |
| `get_battery_thresholds` | Voltage thresholds (critical/low/hysteresis) |
| `get_safety_status` | Current safety settings |
| `get_firmware_version` | Firmware versions (Nordic + MCU) |
| `get_processor_name` | Processor identifiers (Nordic/ST) |
| `get_mac_address` | Bluetooth MAC address |
| `get_board_revision` | PCB board revisions |
| `get_sku` | Product SKU |
| `get_core_uptime` | Uptime in milliseconds |

### Safety & Motor Protection (5 tools)
| Tool | Description |
|------|-------------|
| `set_speed_limit` | Set max speed (0-100%) |
| `set_command_timeout` | Set auto-stop timeout |
| `get_motor_fault_state` | Check for motor faults |
| `enable_motor_stall_notify` | Enable/disable stall detection |
| `enable_motor_fault_notify` | Enable/disable fault detection |

### IR Communication (7 tools)
| Tool | Description |
|------|-------------|
| `send_ir_message` | Send IR code (0-7) |
| `start_ir_broadcasting` | Start robot-to-robot IR broadcasting |
| `stop_ir_broadcasting` | Stop IR broadcasting |
| `start_ir_following` | Follow an IR-broadcasting robot |
| `stop_ir_following` | Stop following |
| `start_ir_evading` | Evade an IR-broadcasting robot |
| `stop_ir_evading` | Stop evading |

## Architecture

### Component Overview

```
MCP Tool Handlers (FastMCP)
    |
    v
Direct Serial Protocol (low-latency)
    |
    +-- Packet Builder (commands.py)
    +-- Serial Connection (direct_serial.py)
    |
    v
Sphero RVR (via /dev/ttyAMA0)
```

### Key Design Patterns

**Direct Serial Protocol**
- Bypasses the Sphero SDK for minimal latency
- Constructs raw SOP/EOP packets directly
- Sub-millisecond command transmission
- Supports all core RVR commands

**Distance-Based Movement**
- `drive_forward(distance)` - Uses RVR's internal position controller
- `drive_backward(distance)` - Accurate reverse movement
- `pivot(degrees)` - Precise rotation using heading control

**Command Queue**
- All hardware commands go through async priority queue
- Priority levels: EMERGENCY (0) -> HIGH (1) -> NORMAL (2) -> LOW (3)
- Per-command timeout enforcement
- Eliminates race conditions in concurrent access

**Atomic State Management**
- Thread-safe with explicit locks
- Validated state transitions
- All changes logged

### Observability

**Structured Logging**
```json
{
  "event": "command_submitted",
  "command_type": "drive_forward",
  "distance": 0.5,
  "timestamp": "2026-01-15T01:23:45.678Z"
}
```

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
- Check serial connection: `ls -l /dev/ttyAMA0`
- Ensure RVR is powered on and charged
- Verify baud rate (default 115200)

**Connection times out**
- RVR might be off or in deep sleep
- Try power cycling the RVR
- Check serial cable connection

### Performance Issues

**Slow response**
- Raspberry Pi 3 may be slower than Pi 4/5
- Reduce sensor streaming frequency
- Close unnecessary applications

### Sensor Issues

**Color detection returns all zeros**
- Ensure RVR is on a non-dark surface
- Try increasing stabilization time
- Check that belly LED is working

### RVR Behavior Issues

**RVR not responding to commands**
- Check if emergency stop is active: `get_safety_status`
- Check speed limit isn't set to 0%
- Try disconnecting and reconnecting

**RVR stops on its own**
- Check command timeout setting (default 5 seconds)
- Disable auto-stop: `set_command_timeout(0)`
- Verify battery level isn't critical

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
    ├── server.py               # MCP server & tool handlers
    │
    ├── protocol/               # Direct serial protocol
    │   ├── __init__.py
    │   ├── commands.py         # Packet builders
    │   ├── direct_serial.py    # Serial connection
    │   └── packet.py           # SOP/EOP framing
    │
    ├── core/                   # Core infrastructure
    │   ├── command_queue.py    # Priority command queue
    │   ├── state_manager.py    # Atomic state management
    │   └── exceptions.py       # Exception hierarchy
    │
    ├── hardware/               # Hardware abstraction
    │   ├── connection_manager.py       # Connection lifecycle
    │   ├── sensor_stream_manager.py    # Sensor streaming
    │   └── safety_monitor.py           # Safety system
    │
    ├── services/               # Application services
    │   ├── movement_service.py
    │   ├── led_service.py
    │   └── ir_service.py
    │
    └── observability/          # Logging
        └── logging.py          # Structured logging
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

### v0.2.3 (2026-01-29)
- **22 new MCP tools** for full SDK sensor coverage:
  - Temperature & thermal protection monitoring
  - System info (firmware, MAC, SKU, uptime, board revision)
  - Extended battery info (voltage, state, thresholds)
  - Motion sensors (encoders, magnetometer with compass heading)
  - Motor protection (fault state, stall/fault notifications)
  - IR follow/evade behaviors
- **Fixed 4 sensor commands** with incorrect protocol parameters
- **Magnetometer heading** - returns `heading` (degrees) and `cardinal` direction

### v0.2.1 (2026-01-15)
- **Direct serial protocol** for low-latency control (bypasses SDK)
- Added `drive_forward` and `drive_backward` with distance in meters
- Added `pivot` command for precise angle rotation
- Removed unused dependencies (prometheus-client, tenacity, nest-asyncio)
- Added pyserial dependency
- Simplified architecture (removed circuit breaker, event bus, metrics)
- No longer requires Sphero SDK installation

### v0.2.0 (2026-01-14)
- Complete architectural rewrite for production reliability
- Added command queue with priority levels
- Added circuit breaker for connection resilience
- Added event bus for sensor distribution
- Added atomic state management
- Added comprehensive observability (logging + metrics)
- Fixed SDK response key parsing (color sensor now works!)

### v0.1.1 (2024-12-XX)
- Added connection timeouts
- Updated documentation

### v0.1.0 (2024-12-XX)
- Initial release

## License

MIT

## Credits

- [FastMCP](https://github.com/jlowin/fastmcp)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Sphero RVR](https://sphero.com/collections/rvr)
