# Hardcoded Values Analysis — juniper-cascor-worker

**Version**: 0.3.0
**Analysis Date**: 2026-04-08
**Analyst**: Claude Code (Automated Code Review)
**Status**: PLANNING ONLY — No source code modifications

---

## Executive Summary

The juniper-cascor-worker codebase contains **~50 hardcoded values** across 7 source files. The `config.py` module provides a `WorkerConfig` dataclass with 8 default values, giving partial coverage. However, protocol message type strings, activation function names, training hyperparameters in `.get()` defaults, and CLI defaults remain unextracted. The codebase is compact (7 source files), making refactoring straightforward.

---

## 1. Existing Constants Infrastructure

| File | Purpose | Coverage |
|------|---------|----------|
| `config.py` (`WorkerConfig`) | Dataclass with heartbeat, reconnect, manager, timeout defaults | Partial — values defined but duplicated in CLI and env defaults |

**Gap**: No dedicated constants module. `WorkerConfig` fields are repeated as environment variable defaults and CLI argument defaults.

---

## 2. Hardcoded Values Inventory

### 2.1 Protocol Message Types (`worker.py`) — NOT COVERED

| Line | Value | Proposed Constant Name |
|------|-------|----------------------|
| 86 | `"connection_established"` | `MSG_TYPE_CONNECTION_ESTABLISHED` |
| 127 | `"register"` | `MSG_TYPE_REGISTER` |
| 134 | `"registration_ack"` | `MSG_TYPE_REGISTRATION_ACK` |
| 146, 173 | `"heartbeat"` | `MSG_TYPE_HEARTBEAT` |
| 171 | `"task_assign"` | `MSG_TYPE_TASK_ASSIGN` |
| 175 | `"result_ack"` | `MSG_TYPE_RESULT_ACK` |
| 178 | `"error"` | `MSG_TYPE_ERROR` |

**Target location**: `juniper_cascor_worker/constants.py`

### 2.2 Activation Function Names (`task_executor.py`) — NOT COVERED

| Line(s) | Value | Proposed Constant Name |
|---------|-------|----------------------|
| 53, 164, 170 | `"sigmoid"` | `ACTIVATION_SIGMOID` |
| 165 | `"tanh"` | `ACTIVATION_TANH` |
| 166 | `"relu"` | `ACTIVATION_RELU` |

### 2.3 Training Hyperparameter Defaults (`task_executor.py`) — NOT COVERED

| Line | Value | Type | Context | Proposed Constant Name |
|------|-------|------|---------|----------------------|
| 59, 78 | `200` | int | Default training epochs | `DEFAULT_TRAINING_EPOCHS` |
| 60, 80 | `0.01` | float | Default learning rate | `DEFAULT_LEARNING_RATE` |
| 61, 81 | `100` | int | Default display frequency | `DEFAULT_DISPLAY_FREQUENCY` |
| 63 | `1.0` | float | Default random value scale | `DEFAULT_RANDOM_VALUE_SCALE` |
| 64 | `1.0` | float | Default random max value | `DEFAULT_RANDOM_MAX_VALUE` |
| 65 | `1.0` | float | Default sequence max value | `DEFAULT_SEQUENCE_MAX_VALUE` |

### 2.4 WebSocket Configuration (`ws_connection.py`) — NOT COVERED

| Line | Value | Type | Context | Proposed Constant Name |
|------|-------|------|---------|----------------------|
| 50 | `"OPEN"` | str | WebSocket state check | `WEBSOCKET_STATE_OPEN` |
| 63 | `"X-API-Key"` | str | Auth header name | `AUTH_HEADER_NAME` |
| 80 | `1.0` | float | Backoff base default | (sync with `WorkerConfig`) |
| 81 | `60.0` | float | Backoff max default | (sync with `WorkerConfig`) |

### 2.5 Config Defaults — Duplicated Across Files

| Config Field | `config.py` | `cli.py` | `env default` | Proposed Constant |
|-------------|-------------|----------|---------------|-------------------|
| Heartbeat interval | `10.0` (L39) | `10.0` (L36) | `"10.0"` (L78) | `DEFAULT_HEARTBEAT_INTERVAL` |
| Manager host | `"127.0.0.1"` (L47) | — | `"127.0.0.1"` (L82) | `DEFAULT_MANAGER_HOST` |
| Manager port | `50000` (L48) | `50000` (L43) | `"50000"` (L83) | `DEFAULT_MANAGER_PORT` |
| MP context | `"forkserver"` (L53) | — | `"forkserver"` (L86) | `DEFAULT_MP_CONTEXT` |
| Num workers | — | `1` (L45) | `"1"` (L85) | `DEFAULT_NUM_WORKERS` |
| Log level | — | `"INFO"` (L49) | — | `DEFAULT_LOG_LEVEL` |

### 2.6 Validation Constants (`config.py`) — NOT COVERED

| Line | Value | Context | Proposed Constant Name |
|------|-------|---------|----------------------|
| 101 | `1` | Min port number | `MIN_PORT` |
| 101-102 | `65535` | Max port number | `MAX_PORT` |

### 2.7 Error Handling (`worker.py`) — NOT COVERED

| Line | Value | Context | Proposed Constant Name |
|------|-------|---------|----------------------|
| 278 | `200` | Max JSON error preview length | `MAX_JSON_ERROR_PREVIEW_LENGTH` |
| 222 | `1.0` | Default denominator fallback | `DEFAULT_DENOMINATOR` |

---

## 3. Coverage Summary

| Category | Total | Covered | Not Covered | Priority |
|----------|-------|---------|-------------|----------|
| Protocol Message Types | 7 | 0 | 7 | **HIGH** |
| Training Hyperparameters | 6 | 0 | 6 | **HIGH** |
| Activation Functions | 3 | 0 | 3 | **MEDIUM** |
| WebSocket Config | 4 | 0 | 4 | **MEDIUM** |
| Config Duplicates | 6 | 3 (partial) | 3 | **MEDIUM** |
| Validation Constants | 2 | 0 | 2 | **LOW** |
| Error Handling | 2 | 0 | 2 | **LOW** |
| **TOTAL** | **~50** | **~3** | **~47** | — |

---

## 4. Remediation Approach

### Recommended: Create `juniper_cascor_worker/constants.py`

Organize into logical sections:

1. **Protocol Message Types** — All WebSocket protocol message type strings
2. **Activation Functions** — Activation function name strings
3. **Training Defaults** — Epochs, learning rate, display frequency, value scales
4. **WebSocket** — State names, header names
5. **Configuration Defaults** — Heartbeat, manager, port, MP context (single source of truth)
6. **Validation** — Port range bounds
7. **Error Handling** — Preview length, fallback values

Then update `config.py`, `cli.py`, `worker.py`, `task_executor.py`, and `ws_connection.py` to import from `constants.py`.

**Key benefit**: Eliminates the 3-way duplication between `config.py`, `cli.py`, and environment variable defaults.

---

## 5. Files Requiring Modification

| File | Action | Replacements |
|------|--------|-------------|
| `juniper_cascor_worker/constants.py` | **NEW** | ~30 constants |
| `juniper_cascor_worker/config.py` | **MODIFY** — reference constants for defaults | 8 |
| `juniper_cascor_worker/cli.py` | **MODIFY** — reference constants for CLI defaults | 4 |
| `juniper_cascor_worker/worker.py` | **MODIFY** — replace protocol strings | 10 |
| `juniper_cascor_worker/task_executor.py` | **MODIFY** — replace training defaults, activation names | 12 |
| `juniper_cascor_worker/ws_connection.py` | **MODIFY** — replace WebSocket constants | 4 |

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Protocol string mismatch with server | Very Low | Critical | Constants match exact current strings; add integration test |
| Training defaults change behavior | Very Low | Medium | Constants preserve exact values |
| Config duplication eliminated correctly | Low | Medium | Unit test all three entry points |
| Import cycle with config.py | Very Low | Low | constants.py has no imports from other worker modules |
