# Changelog

All notable changes to the Sphero RVR MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-01-14

### Changed - Complete Architectural Rewrite

This release is a **complete rewrite** of the Sphero RVR MCP server with production-grade reliability, observability, and performance improvements.

#### Architecture

**Added:**
- **Command Queue**: Priority-based async queue (EMERGENCY → HIGH → NORMAL → LOW) with timeout enforcement
- **Circuit Breaker**: Prevents infinite hangs when RVR is powered off (CLOSED → OPEN → HALF_OPEN states)
- **Event Bus**: Pub/sub pattern for efficient sensor data distribution with backpressure management
- **Atomic State Management**: Thread-safe state with validated transitions and explicit locks
- **Comprehensive Observability**:
  - Structured logging with JSON/console formats (using structlog)
  - 30+ Prometheus metrics for monitoring
  - Health check endpoints

**Removed:**
- Hard-coded 2-second sleep on connection (replaced with event-driven readiness polling)
- Hard-coded 100ms sleep in color detection (now configurable, default 50ms)
- Silent failures throughout codebase (all errors now logged and reported)
- Race conditions in global state (replaced with atomic operations)
- Inefficient sensor handler registration using `dir()` loops (replaced with O(1) pre-built map)

#### Project Structure

**New Modular Architecture:**
```
src/sphero_rvr_mcp/
├── core/                   # Core infrastructure
│   ├── command_queue.py
│   ├── circuit_breaker.py
│   ├── event_bus.py
│   ├── state_manager.py
│   └── exceptions.py
├── hardware/               # Hardware abstraction
│   ├── connection_manager.py
│   ├── sensor_stream_manager.py
│   └── safety_monitor.py
├── services/               # Application services
│   ├── connection_service.py
│   ├── movement_service.py
│   ├── sensor_service.py
│   ├── led_service.py
│   ├── safety_service.py
│   └── ir_service.py
├── tools/                  # MCP tool handlers
│   ├── connection_tools.py
│   ├── movement_tools.py
│   ├── sensor_tools.py
│   ├── led_tools.py
│   ├── safety_tools.py
│   └── ir_tools.py
└── observability/          # Logging & metrics
    ├── logging.py
    ├── metrics.py
    └── health.py
```

**Deprecated (moved to _old.py):**
- `rvr_manager.py` → `rvr_manager_old.py`
- `sensor_manager.py` → `sensor_manager_old.py`
- `safety_controller.py` → `safety_controller_old.py`
- `server.py` → `server_old.py`

#### Bug Fixes

**Critical SDK Response Parsing Fixes:**
- Fixed color detection returning all zeros - SDK uses **camelCase** keys, not snake_case
  - `redChannelValue` (was: `red_channel_value`)
  - `greenChannelValue` (was: `green_channel_value`)
  - `blueChannelValue` (was: `blue_channel_value`)
  - `clearChannelValue` (was: `clear_channel_value`)
- Fixed ambient light sensor parsing - `ambientLightValue` (was: `ambient_light_value`)
- Color detection now correctly identifies colors (verified with blue paper test)

**Connection Improvements:**
- Made firmware version and MAC address queries non-blocking (graceful fallback to "unknown")
- Fixed SerialAsyncDal initialization - added required `loop` parameter
- Fixed parameter names - `device` (was: `port_id`)
- Added resilient error handling for all system info queries

**SDK Compatibility:**
- Re-added `nest-asyncio>=1.6.0` dependency (required for Sphero SDK nested event loops)
- Fixed logging parameter conflicts with structlog (renamed `event` to `event_name`)

#### Features

**Enhanced Battery Status:**
- Added voltage state to battery queries (in addition to percentage)
- Graceful fallback if voltage state unavailable

**New Direct API:**
- Added `api.py` with `RVRClient` class for direct (non-MCP) usage
- Enables standalone scripts and testing without MCP protocol

**Improved Safety:**
- Emergency stop now has highest priority (bypasses queue)
- Speed limiting works for both speed (0-255) and velocity (m/s) modes
- Command timeout with proper task management

**Performance:**
- Connection readiness polling (no fixed sleep)
- Pre-built sensor service map (O(1) lookup)
- Configurable color detection stabilization (50ms default vs 100ms)
- Adaptive timeouts for different command types

#### Configuration

**New Environment Variables:**
- `RVR_WAKE_TIMEOUT` (default: 5.0s)
- `RVR_COMMAND_QUEUE_SIZE` (default: 100)
- `RVR_SENSOR_CACHE_TTL` (default: 2.0s)
- `RVR_LOG_LEVEL` (default: INFO)
- `RVR_LOG_FORMAT` (default: json)
- `RVR_METRICS_ENABLED` (default: true)
- `RVR_METRICS_PORT` (default: 9090)
- `RVR_CIRCUIT_BREAKER_FAILURE_THRESHOLD` (default: 5)
- `RVR_CIRCUIT_BREAKER_TIMEOUT` (default: 30.0s)

#### Dependencies

**Added:**
- `structlog>=24.1.0` - Structured logging
- `prometheus-client>=0.20.0` - Metrics collection
- `tenacity>=8.2.0` - Retry with exponential backoff
- `nest-asyncio>=1.6.0` - SDK compatibility (re-added)

#### Documentation

**New Documentation:**
- `CHANGELOG.md` - This file
- `SDK_KEY_FIXES.md` - Detailed SDK response key fixes
- Updated `README.md` with new architecture, features, and troubleshooting
- Added architecture diagrams and design patterns documentation

**Updated:**
- Complete rewrite of README with new features and architecture
- Enhanced troubleshooting section
- Added metrics and monitoring documentation
- Added direct API usage examples

#### Testing

**Verified Working:**
- ✅ LED control (red, orange, all colors)
- ✅ Color detection (correctly detects blue paper)
- ✅ Ambient light sensor
- ✅ Battery status with voltage state
- ✅ Connection manager (no 2s delay)
- ✅ All SDK response parsing

**Test Scripts Added:**
- `test_leds_fixed.py`
- `test_color_detection.py`
- `test_battery_status.py`
- `test_ambient_light.py`
- `test_all_sdk_keys.py`
- `read_color.py`

### Breaking Changes

⚠️ **This is a major rewrite with breaking changes:**

1. **Module Organization**: Files have been reorganized into `core/`, `hardware/`, `services/`, `tools/`, `observability/` subdirectories
2. **Internal APIs**: If you were importing internal modules directly, paths have changed
3. **Configuration**: Some environment variable names have changed (see Configuration section)
4. **Dependencies**: New required dependencies added

**Migration Guide:**
- If using via MCP: No changes required - MCP tool interface is identical
- If importing modules: Update import paths to new structure
- If using environment variables: Check new variable names

### Known Issues

- Motor temperature queries not supported on this RVR model (`bad_cid` error)
- Battery voltage state returns numeric code, not actual voltage value

---

## [0.1.2] - 2024-XX-XX

### Added
- Connection timeouts to prevent hangs when RVR is powered off

### Changed
- Improved error messages

---

## [0.1.1] - 2024-XX-XX

### Changed
- Updated README for client-agnostic MCP usage

---

## [0.1.0] - 2024-XX-XX

### Added
- Initial release of Sphero RVR MCP Server
- Connection management
- Movement controls (drive_with_heading, drive_tank, drive_rc)
- LED controls (set_all_leds, set_led, turn_leds_off)
- Sensor streaming (accelerometer, gyroscope, IMU, locator, etc.)
- Battery monitoring
- Safety features (speed limiting, emergency stop, command timeout)
- IR communication

### Known Issues
- Hard-coded 2-second sleep on connection
- Color detection returns zeros (SDK key parsing bug)
- Silent failures in error handling
- Race conditions in concurrent access

---

[0.2.0]: https://github.com/jsperson/sphero_rvr_mcp/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/jsperson/sphero_rvr_mcp/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/jsperson/sphero_rvr_mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jsperson/sphero_rvr_mcp/releases/tag/v0.1.0
