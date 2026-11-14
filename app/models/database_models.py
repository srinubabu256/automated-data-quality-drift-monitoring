"""Backward-compatible database models interface."""
from app.database.connection import Base
from app.database.models import (
    BaselineProfile,
    DailyMetric,
    DataQualityAlert,
    DataQualityProfile,
    DataSource,
    DriftAnalysisResult,
    ProcessingError,
    ProcessingRun,
    RawEvent,
    RejectedRecord,
    Transaction,
    TransactionHistory,
)

__all__ = [
    "Base",
    "DataSource",
    "ProcessingRun",
    "Transaction",
    "TransactionHistory",
    "DailyMetric",
    "BaselineProfile",
    "RawEvent",
    "DataQualityProfile",
    "DataQualityAlert",
    "DriftAnalysisResult",
    "RejectedRecord",
    "ProcessingError",
]
