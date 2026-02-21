"""CLI entry point for the JuniperCascor remote worker."""

import argparse
import logging
import signal
import sys

from juniper_cascor_worker.config import WorkerConfig
from juniper_cascor_worker.worker import CandidateTrainingWorker


def main() -> None:
    """Run the remote candidate training worker."""
    parser = argparse.ArgumentParser(
        prog="juniper-cascor-worker",
        description="Remote candidate training worker for JuniperCascor",
    )
    parser.add_argument("--manager-host", default="127.0.0.1", help="Manager hostname (default: 127.0.0.1)")
    parser.add_argument("--manager-port", type=int, default=50000, help="Manager port (default: 50000)")
    parser.add_argument("--authkey", default="juniper", help="Authentication key (default: juniper)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes (default: 1)")
    parser.add_argument("--mp-context", default="forkserver", choices=["forkserver", "spawn", "fork"], help="Multiprocessing context (default: forkserver)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Log level (default: INFO)")
    parser.add_argument("--cascor-path", help="Path to CasCor src directory (added to sys.path)")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.cascor_path:
        sys.path.insert(0, args.cascor_path)

    config = WorkerConfig(
        manager_host=args.manager_host,
        manager_port=args.manager_port,
        authkey=args.authkey,
        num_workers=args.workers,
        mp_context=args.mp_context,
    )

    shutdown_requested = False

    def signal_handler(signum, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            sys.exit(1)
        shutdown_requested = True
        logging.getLogger(__name__).info("Shutdown requested (Ctrl+C again to force)")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    worker = CandidateTrainingWorker(config)
    try:
        worker.connect()
        worker.start()
        logging.getLogger(__name__).info(
            "Worker running (%d processes) — connected to %s:%d. Press Ctrl+C to stop.",
            config.num_workers,
            config.manager_host,
            config.manager_port,
        )

        # Block until shutdown requested
        while not shutdown_requested and worker.is_running:
            signal.pause()

    except KeyboardInterrupt:
        pass
    finally:
        worker.disconnect()
        logging.getLogger(__name__).info("Worker shut down.")


if __name__ == "__main__":
    main()
