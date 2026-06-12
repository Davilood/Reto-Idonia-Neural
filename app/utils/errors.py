from __future__ import annotations


class WorkflowError(Exception):
    """Base exception for controlled workflow failures."""


class InputValidationError(WorkflowError):
    """Raised when user-provided files or fields are invalid."""


class ExternalServiceError(WorkflowError):
    """Raised when an external service returns an unexpected failure."""


class ServiceNotConfiguredError(WorkflowError):
    """Raised when real API mode is requested without an implemented client."""

