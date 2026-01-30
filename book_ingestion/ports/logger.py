"""Pipeline Logger Protocol for logging abstraction."""

from typing import Protocol, Any, Optional


class PipelineLogger(Protocol):
    """
    Protocol for pipeline logging operations.

    Allows callers to provide their own logging implementation
    (e.g., structured logging, cloud logging, etc.)
    """

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an informational message."""
        ...

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message."""
        ...

    def error(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log an error message with optional exception."""
        ...

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message."""
        ...

    def step_started(self, step_name: str, **kwargs: Any) -> None:
        """Log that a pipeline step has started."""
        ...

    def step_completed(self, step_name: str, **kwargs: Any) -> None:
        """Log that a pipeline step has completed."""
        ...

    def step_failed(self, step_name: str, error: Exception, **kwargs: Any) -> None:
        """Log that a pipeline step has failed."""
        ...
