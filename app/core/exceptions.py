"""Centralized Domain Exceptions for YottaFlex Platform."""


class YottaFlexException(Exception):
    """Base exception for all YottaFlex application errors."""

    def __init__(self, message: str, details: str = ""):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return f"{self.message} ({self.details})" if self.details else self.message


class ValidationException(YottaFlexException):
    """Raised when record fails schema or business rule validation."""


class SchemaDriftException(ValidationException):
    """Raised when incoming batch violates expected schema structure."""


class DuplicateBatchException(YottaFlexException):
    """Raised when a batch file with identical SHA-256 hash has already been processed."""


class DuplicateReversalException(YottaFlexException):
    """Raised when a transaction reversal is attempted on an already reversed transaction."""


class ReconciliationException(YottaFlexException):
    """Raised when pipeline reconciliation conservation equation does not balance."""


class BaselineNotFoundException(YottaFlexException):
    """Raised when an active or requested baseline profile version is missing."""


class DriftDetectionException(YottaFlexException):
    """Raised when statistical drift evaluation encounters an unexpected runtime error."""
