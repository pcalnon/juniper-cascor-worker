"""CLI entry point for the JuniperCascor remote worker."""

import argparse
import asyncio
import logging
import os
import signal
import sys
import threading


def main() -> None:
    """Run the remote candidate training worker.

    Default mode: WebSocket-based CascorWorkerAgent.
    Legacy mode (``--legacy``): BaseManager-based CandidateTrainingWorker.
    """
    parser = argparse.ArgumentParser(
        prog="juniper-cascor-worker",
        description="Remote candidate training worker for JuniperCascor",
    )

    # Mode selection
    parser.add_argument("--legacy", action="store_true", help="Use legacy BaseManager worker (deprecated)")

    # WebSocket mode arguments
    parser.add_argument("--server-url", default=None, help="WebSocket server URL (e.g., ws://host:8200/ws/v1/workers)")
    parser.add_argument("--auth-token", default=None, help="Auth token for X-API-Key authentication")
    parser.add_argument("--heartbeat-interval", type=float, default=10.0, help="Heartbeat interval in seconds (default: 10)")
    parser.add_argument("--tls-cert", default=None, help="Client certificate path (for mTLS)")
    parser.add_argument("--tls-key", default=None, help="Client key path (for mTLS)")
    parser.add_argument("--tls-ca", default=None, help="CA certificate path (for mTLS)")

    # Legacy mode arguments
    parser.add_argument("--manager-host", default="127.0.0.1", help="[Legacy] Manager hostname (default: 127.0.0.1)")
    parser.add_argument("--manager-port", type=int, default=50000, help="[Legacy] Manager port (default: 50000)")
    parser.add_argument("--authkey", default=None, help="[Legacy] Authentication key")
    parser.add_argument("--workers", type=int, default=1, help="[Legacy] Number of worker processes (default: 1)")
    parser.add_argument("--mp-context", default="forkserver", choices=["forkserver", "spawn", "fork"], help="[Legacy] Multiprocessing context (default: forkserver)")

    # Shared arguments
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Log level (default: INFO)")
    parser.add_argument("--cascor-path", help="Path to CasCor src directory (added to sys.path)")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.cascor_path:
        sys.path.insert(0, args.cascor_path)

    if args.legacy:
        _run_legacy(args)
    else:
        _run_websocket(args)


def _run_websocket(args: argparse.Namespace) -> None:
    """Run the WebSocket-based CascorWorkerAgent."""
    from juniper_cascor_worker.config import WorkerConfig
    from juniper_cascor_worker.worker import CascorWorkerAgent

    server_url = args.server_url or os.environ.get("CASCOR_SERVER_URL", "")
    auth_token = args.auth_token or os.environ.get("CASCOR_AUTH_TOKEN", "")

    config = WorkerConfig(
        server_url=server_url,
        auth_token=auth_token,
        heartbeat_interval=args.heartbeat_interval,
        tls_cert=args.tls_cert,
        tls_key=args.tls_key,
        tls_ca=args.tls_ca,
    )
    config.validate(legacy=False)

    agent = CascorWorkerAgent(config)

    # Cross-platform shutdown via threading.Event (replaces signal.pause)
    shutdown_event = threading.Event()

    def signal_handler(signum, frame):
        if shutdown_event.is_set():
            sys.exit(1)
        logging.getLogger(__name__).info("Shutdown requested (Ctrl+C again to force)")
        agent.stop()
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logging.getLogger(__name__).info("Starting WebSocket worker — connecting to %s", config.server_url)

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        pass

    logging.getLogger(__name__).info("Worker shut down.")


def _run_legacy(args: argparse.Namespace) -> None:
    """Run the legacy BaseManager-based CandidateTrainingWorker."""
    from juniper_cascor_worker.config import WorkerConfig
    from juniper_cascor_worker.worker import CandidateTrainingWorker

    authkey = args.authkey or os.environ.get("CASCOR_AUTHKEY", "")

    config = WorkerConfig(
        manager_host=args.manager_host,
        manager_port=args.manager_port,
        authkey=authkey,
        num_workers=args.workers,
        mp_context=args.mp_context,
    )
    config.validate(legacy=True)

    # Cross-platform shutdown via threading.Event (replaces signal.pause)
    shutdown_event = threading.Event()

    def signal_handler(signum, frame):
        if shutdown_event.is_set():
            sys.exit(1)
        shutdown_event.set()
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

        # Block until shutdown — cross-platform (no signal.pause)
        shutdown_event.wait()

    except KeyboardInterrupt:
        pass
    finally:
        worker.disconnect()
        logging.getLogger(__name__).info("Worker shut down.")


if __name__ == "__main__":
    main()
