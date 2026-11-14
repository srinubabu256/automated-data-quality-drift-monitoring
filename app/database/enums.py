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
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DriftType(str, Enum):
    VOLUME = "VOLUME"
    NULL_RATE = "NULL_RATE"
    DISTRIBUTION_PSI = "DISTRIBUTION_PSI"
    DISTRIBUTION_KS = "DISTRIBUTION_KS"
    DISTRIBUTION_CHISQUARE = "DISTRIBUTION_CHISQUARE"
    FRESHNESS = "FRESHNESS"
    SCHEMA = "SCHEMA"


class DetectionMethod(str, Enum):
    PERCENTAGE_CHANGE = "PERCENTAGE_CHANGE"
    PERCENTAGE_POINT_SHIFT = "PERCENTAGE_POINT_SHIFT"
    PSI = "PSI"
    KOLMOGOROV_SMIRNOV = "KOLMOGOROV_SMIRNOV"
    CHI_SQUARE = "CHI_SQUARE"
    LATENCY_SHIFT = "LATENCY_SHIFT"
    SCHEMA_DIFF = "SCHEMA_DIFF"


class DimensionType(str, Enum):
    TOTAL = "TOTAL"
    PRODUCT = "PRODUCT"
    CUSTOMER = "CUSTOMER"
