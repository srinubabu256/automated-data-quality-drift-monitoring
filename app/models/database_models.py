"""SQLAlchemy declarative database models for YottaFlex Data Engineering Challenge."""
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    Date,
    Text,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    system_type = Column(String(64), nullable=False, default="CSV_BATCH")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    run_id = Column(String(64), primary_key=True)
    source_file = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="PENDING")
    input_count = Column(Integer, default=0, nullable=False)
    accepted_count = Column(Integer, default=0, nullable=False)
    rejected_count = Column(Integer, default=0, nullable=False)
    duplicate_count = Column(Integer, default=0, nullable=False)
    processed_count = Column(Integer, default=0, nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    execution_duration_sec = Column(Float, default=0.0)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    raw_events = relationship("RawEvent", back_populates="processing_run", cascade="all, delete-orphan")
    rejected_records = relationship("RejectedRecord", back_populates="processing_run", cascade="all, delete-orphan")
    quality_profile = relationship("DataQualityProfile", back_populates="processing_run", uselist=False, cascade="all, delete-orphan")
    alerts = relationship("DataQualityAlert", back_populates="processing_run", cascade="all, delete-orphan")
    errors = relationship("ProcessingError", back_populates="processing_run", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(String(64), primary_key=True)
    customer_id = Column(String(64), nullable=False, index=True)
    product_id = Column(String(64), nullable=False, index=True)
    current_amount = Column(Numeric(14, 2), nullable=False, default=0.0)
    currency = Column(String(3), nullable=False, default="USD")
    status = Column(String(32), nullable=False, default="ACTIVE")  # ACTIVE, REVERSED
    is_reversed = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    first_event_timestamp = Column(DateTime, nullable=False)
    latest_event_timestamp = Column(DateTime, nullable=False)
    latest_event_id = Column(String(64), nullable=False)
    last_run_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    history = relationship("TransactionHistory", back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tx_status_updated", "status", "updated_at"),
        Index("idx_tx_customer_product", "customer_id", "product_id"),
    )


class TransactionHistory(Base):
    __tablename__ = "transaction_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String(64), ForeignKey("transactions.transaction_id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = Column(String(64), nullable=False, index=True)
    event_type = Column(String(32), nullable=False)
    previous_amount = Column(Numeric(14, 2), nullable=True)
    new_amount = Column(Numeric(14, 2), nullable=False)
    event_timestamp = Column(DateTime, nullable=False)
    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    run_id = Column(String(64), nullable=False)

    transaction = relationship("Transaction", back_populates="history")

    __table_args__ = (
        Index("idx_tx_hist_tx_id", "transaction_id", "event_timestamp"),
    )


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_date = Column(Date, nullable=False, index=True)
    dimension_type = Column(String(32), nullable=False, default="TOTAL")  # TOTAL, PRODUCT
    dimension_value = Column(String(64), nullable=False, default="ALL")
    total_transactions = Column(Integer, nullable=False, default=0)
    total_amount = Column(Numeric(16, 2), nullable=False, default=0.0)
    active_customers = Column(Integer, nullable=False, default=0)
    active_products = Column(Integer, nullable=False, default=0)
    avg_amount = Column(Numeric(14, 2), nullable=False, default=0.0)
    min_amount = Column(Numeric(14, 2), nullable=False, default=0.0)
    max_amount = Column(Numeric(14, 2), nullable=False, default=0.0)
    null_rate = Column(Float, nullable=False, default=0.0)
    record_volume = Column(Integer, nullable=False, default=0)
    event_freshness_sec = Column(Float, nullable=False, default=0.0)
    ingestion_freshness_sec = Column(Float, nullable=False, default=0.0)
    rejected_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    run_id = Column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("metric_date", "dimension_type", "dimension_value", name="uq_daily_metric_date_dim"),
        Index("idx_daily_metric_date", "metric_date"),
    )


class BaselineProfile(Base):
    __tablename__ = "baseline_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(32), unique=True, nullable=False)
    baseline_name = Column(String(64), nullable=False)
    record_volume = Column(Integer, nullable=False, default=1000)
    null_rate = Column(Float, nullable=False, default=0.02)
    mean_amount = Column(Float, nullable=False, default=150.0)
    std_amount = Column(Float, nullable=False, default=50.0)
    min_amount = Column(Float, nullable=False, default=5.0)
    max_amount = Column(Float, nullable=False, default=500.0)
    median_amount = Column(Float, nullable=False, default=140.0)
    p95_amount = Column(Float, nullable=False, default=300.0)
    event_freshness_sec = Column(Float, nullable=False, default=3600.0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RawEvent(Base):
    __tablename__ = "raw_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    run_id = Column(String(64), ForeignKey("processing_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id = Column(String(64), nullable=False, index=True)
    customer_id = Column(String(64), nullable=True, index=True)
    product_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(32), nullable=False)  # NEW, UPDATE, REVERSAL
    amount = Column(Numeric(14, 2), nullable=True)
    currency = Column(String(3), nullable=True, default="USD")
    event_timestamp = Column(DateTime, nullable=False, index=True)
    ingestion_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    source_system = Column(String(64), nullable=True)
    source_file = Column(String(255), nullable=True)
    raw_payload = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="ACCEPTED")  # ACCEPTED, DUPLICATE, PROCESSED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    processing_run = relationship("ProcessingRun", back_populates="raw_events")

    __table_args__ = (
        Index("idx_raw_event_tx_type", "transaction_id", "event_type"),
    )


class DataQualityProfile(Base):
    __tablename__ = "data_quality_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("processing_runs.run_id", ondelete="CASCADE"), unique=True, nullable=False)
    batch_volume = Column(Integer, nullable=False, default=0)
    null_rate = Column(Float, nullable=False, default=0.0)
    mean_amount = Column(Float, nullable=False, default=0.0)
    std_amount = Column(Float, nullable=False, default=0.0)
    min_amount = Column(Float, nullable=False, default=0.0)
    max_amount = Column(Float, nullable=False, default=0.0)
    median_amount = Column(Float, nullable=False, default=0.0)
    p95_amount = Column(Float, nullable=False, default=0.0)
    event_freshness_sec = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    processing_run = relationship("ProcessingRun", back_populates="quality_profile")


class DataQualityAlert(Base):
    __tablename__ = "data_quality_alerts"

    alert_id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("processing_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    metric_name = Column(String(64), nullable=False)
    baseline_value = Column(Float, nullable=False)
    current_value = Column(Float, nullable=False)
    difference = Column(Float, nullable=False)
    pct_change = Column(Float, nullable=False)
    severity = Column(String(32), nullable=False)  # INFO, WARNING, CRITICAL
    explanation = Column(Text, nullable=False)
    suggested_action = Column(Text, nullable=False)
    is_resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    processing_run = relationship("ProcessingRun", back_populates="alerts")

    __table_args__ = (
        UniqueConstraint("run_id", "metric_name", name="uq_run_metric_alert"),
    )


class RejectedRecord(Base):
    __tablename__ = "rejected_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("processing_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    source_file = Column(String(255), nullable=False)
    line_number = Column(Integer, nullable=True)
    raw_data = Column(Text, nullable=False)
    rejection_reason = Column(Text, nullable=False)
    rejection_code = Column(String(64), nullable=False)
    rejected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    processing_run = relationship("ProcessingRun", back_populates="rejected_records")


class ProcessingError(Base):
    __tablename__ = "processing_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("processing_runs.run_id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(64), nullable=False)
    error_type = Column(String(64), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    processing_run = relationship("ProcessingRun", back_populates="errors")
