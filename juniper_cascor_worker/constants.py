"""Constants for the JuniperCascor worker package.

Single source of truth for protocol message types, configuration defaults,
activation function names, validation bounds, and environment variable names
used across the worker codebase. Eliminates duplication previously spread
across :mod:`juniper_cascor_worker.config`, :mod:`juniper_cascor_worker.cli`,
:mod:`juniper_cascor_worker.worker`, :mod:`juniper_cascor_worker.task_executor`,
and :mod:`juniper_cascor_worker.ws_connection`.

Protocol message type strings MUST remain bit-identical to the canonical
definitions on the juniper-cascor server side
(``juniper-cascor/src/api/workers/protocol.py``::``MessageType``). Any change
here MUST be coordinated with the server's ``MessageType`` enum.
"""

from typing import Final

# ---------------------------------------------------------------------------
# Protocol Message Types (WIRE PROTOCOL — must match juniper-cascor server)
# ---------------------------------------------------------------------------
# Mirrors juniper-cascor/src/api/workers/protocol.py::MessageType plus the
# server-only `connection_established` and `registration_ack`/`result_ack`
# acknowledgement strings emitted by the worker_stream endpoint.

MSG_TYPE_CONNECTION_ESTABLISHED: Final[str] = "connection_established"
MSG_TYPE_REGISTER: Final[str] = "register"
MSG_TYPE_REGISTRATION_ACK: Final[str] = "registration_ack"
MSG_TYPE_HEARTBEAT: Final[str] = "heartbeat"
MSG_TYPE_TASK_ASSIGN: Final[str] = "task_assign"
MSG_TYPE_TASK_RESULT: Final[str] = "task_result"
MSG_TYPE_RESULT_ACK: Final[str] = "result_ack"
MSG_TYPE_TOKEN_REFRESH: Final[str] = "token_refresh"  # nosec B105 — protocol message type, not a password
MSG_TYPE_ERROR: Final[str] = "error"

# ---------------------------------------------------------------------------
# Activation Function Names
# ---------------------------------------------------------------------------
# These string identifiers map to (function, derivative) tuples in
# task_executor._get_activation_function and must match the names recognized
# by the cascor CandidateUnit.

ACTIVATION_SIGMOID: Final[str] = "sigmoid"
ACTIVATION_TANH: Final[str] = "tanh"
ACTIVATION_RELU: Final[str] = "relu"

# Default activation used when an unrecognized name is supplied.
DEFAULT_ACTIVATION: Final[str] = ACTIVATION_SIGMOID

# ---------------------------------------------------------------------------
# Training Hyperparameter Defaults
# ---------------------------------------------------------------------------
# Used as fallback values for training_params.get(...) lookups in
# task_executor.execute_training_task. These represent the worker's
# defaults when the server does not include the field — server-supplied
# values always take precedence.

DEFAULT_TRAINING_EPOCHS: Final[int] = 200
DEFAULT_LEARNING_RATE: Final[float] = 0.01
DEFAULT_DISPLAY_FREQUENCY: Final[int] = 100
DEFAULT_RANDOM_VALUE_SCALE: Final[float] = 1.0
DEFAULT_RANDOM_MAX_VALUE: Final[float] = 1.0
DEFAULT_SEQUENCE_MAX_VALUE: Final[float] = 1.0

# CandidateUnit log level (passed to CandidateUnit__log_level_name).
CANDIDATE_UNIT_LOG_LEVEL: Final[str] = "INFO"

# ---------------------------------------------------------------------------
# WebSocket Connection
# ---------------------------------------------------------------------------

# WebSocket protocol state name reported as "OPEN" when the connection is up.
WEBSOCKET_STATE_OPEN: Final[str] = "OPEN"

# Header name used to authenticate the worker with the cascor server.
AUTH_HEADER_NAME: Final[str] = "X-API-Key"  # nosec B105 — header name, not a password

# WebSocket URL scheme prefixes accepted by the worker.
WS_SCHEME_INSECURE: Final[str] = "ws://"
WS_SCHEME_SECURE: Final[str] = "wss://"
VALID_WS_SCHEMES: Final[tuple[str, ...]] = (WS_SCHEME_INSECURE, WS_SCHEME_SECURE)

# ---------------------------------------------------------------------------
# Configuration Defaults — Single Source of Truth
# ---------------------------------------------------------------------------
# These defaults were previously duplicated across config.py, cli.py, and the
# WorkerConfig.from_env environment variable defaults. Centralizing them here
# eliminates the 3-way duplication.

# Heartbeat / reconnect timing
DEFAULT_HEARTBEAT_INTERVAL: Final[float] = 10.0
DEFAULT_RECONNECT_BACKOFF_BASE: Final[float] = 1.0
DEFAULT_RECONNECT_BACKOFF_MAX: Final[float] = 60.0

# METRICS-MON R1.3 / seed-04: HTTP health server defaults.
# Bound to localhost by default; operators set CASCOR_WORKER_HEALTH_BIND=0.0.0.0
# explicitly when running under k8s with httpGet probes.
DEFAULT_HEALTH_PORT: Final[int] = 8210
DEFAULT_HEALTH_BIND: Final[str] = "127.0.0.1"
# Liveness tick budget. The tick is purely in-process (consults
# WS-connection-state + counter timestamp) and 250 ms catches event-loop
# stalls that the WS-level heartbeat cannot.
LIVENESS_TICK_BUDGET_MS: Final[int] = 250
# Read timeout for incoming HTTP request bytes; bounds malformed-request DoS.
HEALTH_REQUEST_READ_TIMEOUT_S: Final[float] = 2.0
# Cap on accepted request bytes — covers method line + headers; a real
# probe request is < 200 bytes.
HEALTH_REQUEST_MAX_BYTES: Final[int] = 4096

# Per-task training timeout (seconds). 1 hour by default.
DEFAULT_TASK_TIMEOUT: Final[float] = 3600.0

# Legacy BaseManager mode defaults
DEFAULT_MANAGER_HOST: Final[str] = "127.0.0.1"
DEFAULT_MANAGER_PORT: Final[int] = 50000
DEFAULT_NUM_WORKERS: Final[int] = 1
DEFAULT_TASK_QUEUE_TIMEOUT: Final[float] = 5.0
DEFAULT_STOP_TIMEOUT: Final[int] = 10
DEFAULT_MP_CONTEXT: Final[str] = "forkserver"

# Allowed multiprocessing start methods for the legacy manager.
MP_CONTEXT_FORKSERVER: Final[str] = "forkserver"
MP_CONTEXT_SPAWN: Final[str] = "spawn"
MP_CONTEXT_FORK: Final[str] = "fork"
VALID_MP_CONTEXTS: Final[tuple[str, ...]] = (
    MP_CONTEXT_FORKSERVER,
    MP_CONTEXT_SPAWN,
    MP_CONTEXT_FORK,
)

# Logging defaults shared by CLI and runtime.
DEFAULT_LOG_LEVEL: Final[str] = "INFO"
VALID_LOG_LEVELS: Final[tuple[str, ...]] = ("DEBUG", "INFO", "WARNING", "ERROR")
LOG_FORMAT: Final[str] = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# ---------------------------------------------------------------------------
# Environment Variable Names
# ---------------------------------------------------------------------------
# Eliminates string duplication between config.py and cli.py for the env vars
# that the worker reads.

ENV_SERVER_URL: Final[str] = "CASCOR_SERVER_URL"
ENV_AUTH_TOKEN: Final[str] = "CASCOR_AUTH_TOKEN"  # nosec B105 — env var name, not a token value
ENV_API_KEY: Final[str] = "CASCOR_API_KEY"  # nosec B105 — env var name, not a key value
ENV_HEARTBEAT_INTERVAL: Final[str] = "CASCOR_HEARTBEAT_INTERVAL"
ENV_HEALTH_PORT: Final[str] = "CASCOR_WORKER_HEALTH_PORT"
ENV_HEALTH_BIND: Final[str] = "CASCOR_WORKER_HEALTH_BIND"
ENV_TASK_TIMEOUT: Final[str] = "CASCOR_TASK_TIMEOUT"
ENV_TLS_CERT: Final[str] = "CASCOR_TLS_CERT"
ENV_TLS_KEY: Final[str] = "CASCOR_TLS_KEY"
ENV_TLS_CA: Final[str] = "CASCOR_TLS_CA"
ENV_MANAGER_HOST: Final[str] = "CASCOR_MANAGER_HOST"
ENV_MANAGER_PORT: Final[str] = "CASCOR_MANAGER_PORT"
ENV_AUTHKEY: Final[str] = "CASCOR_AUTHKEY"  # nosec B105 — env var name, not an auth key value
ENV_NUM_WORKERS: Final[str] = "CASCOR_NUM_WORKERS"
ENV_MP_CONTEXT: Final[str] = "CASCOR_MP_CONTEXT"

# ---------------------------------------------------------------------------
# Validation Bounds
# ---------------------------------------------------------------------------

# Inclusive port range for the legacy BaseManager port validator.
MIN_PORT: Final[int] = 1
MAX_PORT: Final[int] = 65535

# Minimum allowed worker count for the legacy mode.
MIN_NUM_WORKERS: Final[int] = 1

# ---------------------------------------------------------------------------
# Error Handling / Diagnostics
# ---------------------------------------------------------------------------

# Maximum number of characters of an invalid JSON message logged for diagnostics.
MAX_JSON_ERROR_PREVIEW_LENGTH: Final[int] = 200

# Fallback denominator value used in the task_result emitted on timeout.
DEFAULT_DENOMINATOR: Final[float] = 1.0

# Sentinel "no best correlation index" value emitted in failure paths.
NO_BEST_CORR_IDX: Final[int] = -1

# Sentinel "no epochs completed" value emitted in failure paths.
NO_EPOCHS_COMPLETED: Final[int] = 0

# Default initial correlation when no training has occurred.
DEFAULT_CORRELATION: Final[float] = 0.0

# Default initial numerator when no training has occurred.
DEFAULT_NUMERATOR: Final[float] = 0.0

# ---------------------------------------------------------------------------
# Binary Frame Encoding
# ---------------------------------------------------------------------------
# Constants for the BinaryFrame encode/decode helpers in worker.py. Mirrors
# the canonical definitions in juniper-cascor's protocol.BinaryFrame.

# Encoding for dtype strings stored in binary frame headers.
BINARY_FRAME_DTYPE_ENCODING: Final[str] = "utf-8"

# struct format characters used by the binary frame header.
BINARY_FRAME_HEADER_LENGTH_FORMAT: Final[str] = "<I"
BINARY_FRAME_HEADER_LENGTH_BYTES: Final[int] = 4
