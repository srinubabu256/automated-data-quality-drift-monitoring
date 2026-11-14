"""Domain enums for transaction processing and status tracking."""
from enum import Enum


class EventType(str, Enum):
    NEW = "NEW"
    UPDATE = "UPDATE"
    REVERSAL = "REVERSAL"


class RecordStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    PROCESSED = "PROCESSED"
    REVERSED = "REVERSED"


class BatchStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRIED = "RETRIED"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DimensionType(str, Enum):
    TOTAL = "TOTAL"
    PRODUCT = "PRODUCT"
    CUSTOMER = "CUSTOMER"

