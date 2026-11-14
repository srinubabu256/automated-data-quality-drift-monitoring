"""Pydantic schemas for API request and response serialization."""
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    environment: str
    timestamp: datetime
    database: str


class ProcessingRunResponse(BaseModel):
    run_id: str
    source_file: str
    file_hash: str
    status: str
    input_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    processed_count: int
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_duration_sec: Optional[float] = None
    failure_reason: Optional[str] = None

    class Config:
        from_attributes = True


class BatchUploadResponse(BaseModel):
    run_id: str
    status: str
    input_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    processed_count: int
    affected_dates: List[str]
    duration_sec: float
    reconciliation_passed: bool
    alerts_generated: int


class DailyMetricResponse(BaseModel):
    metric_date: date
    dimension_type: str
    dimension_value: str
    total_transactions: int
    total_amount: float
    active_customers: int
    active_products: int
    avg_amount: float
    min_amount: float
    max_amount: float
    null_rate: float
    record_volume: int
    event_freshness_sec: float
    ingestion_freshness_sec: float
    rejected_count: int
    duplicate_count: int
    computed_at: datetime
    run_id: Optional[str] = None

    class Config:
        from_attributes = True


class DataQualityProfileResponse(BaseModel):
    id: int
    run_id: str
    batch_volume: int
    null_rate: float
    mean_amount: float
    std_amount: float
    min_amount: float
    max_amount: float
    median_amount: float
    p95_amount: float
    event_freshness_sec: float
    created_at: datetime

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    alert_id: str
    run_id: str
    metric_name: str
    baseline_value: float
    current_value: float
    difference: float
    pct_change: float
    severity: str
    explanation: str
    suggested_action: str
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RejectedRecordResponse(BaseModel):
    id: int
    run_id: str
    source_file: str
    line_number: Optional[int] = None
    raw_data: str
    rejection_reason: str
    rejection_code: str
    rejected_at: datetime

    class Config:
        from_attributes = True


class ReconciliationResponse(BaseModel):
    run_id: str
    source_file: Optional[str] = None
    reconciled: bool
    status: str
    equation: str
    counts: Dict[str, Any]
    database_audit: Dict[str, Any]
    financial_audit: Dict[str, Any]
    execution_metadata: Dict[str, Any]

