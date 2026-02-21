"""Custom exceptions for the JuniperCascor worker package."""


class WorkerError(Exception):
    """Base exception for all worker errors."""

    pass


class WorkerConnectionError(WorkerError):
    """Raised when connection to the training manager fails."""

    pass


class WorkerConfigError(WorkerError):
    """Raised when worker configuration is invalid."""

    pass
