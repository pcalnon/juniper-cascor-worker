# juniper-cascor-worker

Remote candidate training worker for the JuniperCascor cascade correlation neural network service.

## Overview

This package enables distributed candidate training by connecting to a CasCor
CandidateTrainingManager and processing training tasks on remote hardware.

## Installation

```bash
pip install juniper-cascor-worker
```

**Note:** This package requires the JuniperCascor source code to be importable
on the worker machine (the worker runs CasCor's training code locally).

## CLI Usage

```bash
# Basic usage
juniper-cascor-worker --manager-host 192.168.1.100 --manager-port 50000 --workers 4

# With CasCor source path
juniper-cascor-worker --manager-host 192.168.1.100 --cascor-path /opt/juniper-cascor/src --workers 8

# Full options
juniper-cascor-worker \
    --manager-host 192.168.1.100 \
    --manager-port 50000 \
    --authkey my-secret-key \
    --workers 4 \
    --mp-context forkserver \
    --log-level INFO
```

## Python API

```python
from juniper_cascor_worker import CandidateTrainingWorker, WorkerConfig

config = WorkerConfig(
    manager_host="192.168.1.100",
    manager_port=50000,
    authkey="my-secret-key",
    num_workers=4,
)

with CandidateTrainingWorker(config) as worker:
    worker.start()
    # Workers process tasks from the remote queue
    input("Press Enter to stop...")
    worker.stop()
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CASCOR_MANAGER_HOST` | Manager hostname | 127.0.0.1 |
| `CASCOR_MANAGER_PORT` | Manager port | 50000 |
| `CASCOR_AUTHKEY` | Authentication key | juniper |
| `CASCOR_NUM_WORKERS` | Worker count | 1 |
| `CASCOR_MP_CONTEXT` | Multiprocessing method | forkserver |

## License

MIT License - see [LICENSE](LICENSE) for details.
