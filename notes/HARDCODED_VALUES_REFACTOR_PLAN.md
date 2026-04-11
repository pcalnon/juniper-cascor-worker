# Hardcoded Values Refactor Plan — juniper-cascor-worker

**Version**: 0.3.0
**Created**: 2026-04-08
**Status**: PLANNING — No source code modifications
**Companion Document**: `HARDCODED_VALUES_ANALYSIS.md`

---

## Phase 1: Constants Infrastructure (Priority: HIGH)

### Step 1.1: Create Constants Module

**Task**: Create `juniper_cascor_worker/constants.py` (~30 constants)

**Sections**:
1. Protocol Message Types (7 constants: connection_established, register, registration_ack, heartbeat, task_assign, result_ack, error)
2. Activation Functions (3 constants: sigmoid, tanh, relu)
3. Training Defaults (6 constants: epochs, learning rate, display frequency, value scales)
4. WebSocket Configuration (state names, header names)
5. Configuration Defaults (heartbeat, manager host/port, MP context, num workers, log level)
6. Validation Constants (port range bounds)
7. Error Handling (JSON preview length, default denominator)

### Step 1.2: Eliminate Config Duplication

**Task**: Update `config.py` and `cli.py` to reference `constants.py` for all default values, eliminating the 3-way duplication.

---

## Phase 2: Source File Refactor (Priority: HIGH)

### Step 2.1: Refactor Worker Protocol

**File**: `worker.py` — Replace 10 protocol message type strings with constants

### Step 2.2: Refactor Task Executor

**File**: `task_executor.py` — Replace 12 training defaults and activation names

### Step 2.3: Refactor WebSocket Connection

**File**: `ws_connection.py` — Replace 4 WebSocket-related strings

### Step 2.4: Refactor Config Defaults

**File**: `config.py` — Reference constants for 8 dataclass field defaults and 8 env var defaults

### Step 2.5: Refactor CLI Defaults

**File**: `cli.py` — Reference constants for 4 argparse defaults

---

## Phase 3: Validation (Priority: HIGH)

### Step 3.1: Run Full Test Suite

```bash
pytest tests/ -v
```

### Step 3.2: Pre-commit Hooks

```bash
pre-commit run --all-files
```

### Step 3.3: Protocol Compatibility Test

**Critical**: Verify protocol message type strings match the juniper-cascor server expectations exactly. Run integration test if available.

---

## Phase 4: Documentation & Release (Priority: MEDIUM)

### Step 4.1: Update AGENTS.md
### Step 4.2: Update CHANGELOG.md
### Step 4.3: Create Release Description
