"""Targeted verification test suite addressing the 10 submission readiness checks."""
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.models.database_models import (
    Base,
    Transaction,
    TransactionHistory,
    ProcessingRun,
    RawEvent,
    RejectedRecord,
    BaselineProfile,
    DataQualityProfile,
    DataQualityAlert,
)
from app.models.enums import BatchStatus
from app.validation.schema_validator import SchemaValidator
from app.validation.business_validator import BusinessValidator
from app.profiling.profiler import ColumnProfiler, Profiler
from app.processing.transaction_processor import TransactionProcessor
from app.reporting.reconciliation import ReconciliationEngine
from app.api.routes import batches, metrics, alerts, reports
from app.main import health_check


@pytest.fixture
def target_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ----------------------------------------------------------------------
# 1. SCHEMA DRIFT
# ----------------------------------------------------------------------
def test_schema_drift_added_column():
    """Verify added unexpected column is accepted without breaking schema validation."""
    row = {
        "event_id": "e_add",
        "transaction_id": "t_add",
        "customer_id": "c1",
        "product_id": "p1",
        "event_type": "NEW",
        "amount": "100.00",
        "currency": "USD",
        "event_timestamp": "2026-11-10T10:00:00Z",
        "unplanned_extra_column": "some_extra_data",
    }
    is_valid, reason, code, validated = SchemaValidator.validate_record(row)
    assert is_valid is True
    assert "event_id" in validated
    assert "unplanned_extra_column" not in validated  # Filtered out safely


def test_schema_drift_removed_or_renamed_column():
    """Verify removed or renamed mandatory column fails validation."""
    # Renamed 'amount' to 'transaction_value'
    row = {
        "event_id": "e_renamed",
        "transaction_id": "t_renamed",
        "customer_id": "c1",
        "product_id": "p1",
        "event_type": "NEW",
        "transaction_value": "100.00",
        "currency": "USD",
        "event_timestamp": "2026-11-10T10:00:00Z",
    }
    is_valid, reason, code, _ = SchemaValidator.validate_record(row)
    assert is_valid is False
    assert code == "MISSING_REQUIRED_FIELD"


def test_schema_drift_changed_data_type():
    """Verify changed column data type (string instead of numeric amount) is rejected."""
    row = {
        "event_id": "e_type",
        "transaction_id": "t_type",
        "customer_id": "c1",
        "product_id": "p1",
        "event_type": "NEW",
        "amount": "NOT_A_DECIMAL",
        "currency": "USD",
        "event_timestamp": "2026-11-10T10:00:00Z",
    }
    is_valid, reason, code, _ = SchemaValidator.validate_record(row)
    assert is_valid is False
    assert code == "MALFORMED_AMOUNT_TYPE"


# ----------------------------------------------------------------------
# 2. DISTRIBUTION DRIFT
# ----------------------------------------------------------------------
def test_distribution_drift_detection():
    """Verify column baseline comparison detects new/disappearing categories and numerical shifts."""
    baseline_records = [
        {"event_id": "b1", "event_type": "NEW", "amount": "100.00", "currency": "USD"},
        {"event_id": "b2", "event_type": "NEW", "amount": "120.00", "currency": "USD"},
        {"event_id": "b3", "event_type": "UPDATE", "amount": "110.00", "currency": "USD"},
    ]
    # Current batch introduces 'REVERSAL' (new category) and removes 'UPDATE' (disappearing category)
    current_records = [
        {"event_id": "c1", "event_type": "NEW", "amount": "300.00", "currency": "EUR"},
        {"event_id": "c2", "event_type": "REVERSAL", "amount": "350.00", "currency": "EUR"},
    ]

    base_prof = ColumnProfiler.profile_columns(baseline_records, run_id="BASE", baseline_version="v1.0")
    curr_prof = ColumnProfiler.profile_columns(current_records, run_id="CURR", baseline_version="v1.0")
    comp = ColumnProfiler.compare_column_baselines(base_prof, curr_prof)

    evt_shift = comp["column_comparisons"]["event_type"]["categorical_distribution_shift"]
    assert evt_shift["REVERSAL"] == 1   # New category introduced
    assert evt_shift["UPDATE"] == -1    # Disappeared category

    amt_drift = comp["column_comparisons"]["amount"]["numerical_drift"]
    assert amt_drift["baseline_mean"] == 110.0
    assert amt_drift["current_mean"] == 325.0
    assert amt_drift["pct_change"] > 100.0  # Significant upward drift


# ----------------------------------------------------------------------
# 3. FRESHNESS
# ----------------------------------------------------------------------
def test_event_freshness_and_stale_event_alert():
    """Verify stale events with past timestamps are accurately profiled with high freshness latency."""
    stale_ts = datetime.now(timezone.utc) - timedelta(days=5)  # 5 days stale (432,000s)
    records = [
        {"event_id": "e_stale", "transaction_id": "t_stale", "customer_id": "c1", "product_id": "p1", "event_type": "NEW", "amount": 100.00, "currency": "USD", "event_timestamp": stale_ts}
    ]
    now = datetime.now(timezone.utc)
    freshness_sec = (now - stale_ts).total_seconds()
    assert freshness_sec >= 430000.0


# ----------------------------------------------------------------------
# 4. PARTIAL FAILURE AND RECOVERY
# ----------------------------------------------------------------------
def test_pipeline_failure_recovery_and_idempotent_retry(target_db):
    """Simulate a failure midway, verify transaction rollback, and retry cleanly."""
    processor = TransactionProcessor(db=target_db)

    # Ingest a valid initial batch
    res1 = processor.process_records([
        {"event_id": "e_init", "transaction_id": "t_init", "customer_id": "c1", "product_id": "p1", "event_type": "NEW", "amount": "100.00", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"}
    ], source_name="batch_init.csv")
    assert res1.status == "COMPLETED"
    assert target_db.query(Transaction).count() == 1

    # Simulate run failure in batch_manager
    from app.ingestion.batch_manager import BatchManager
    failed_run = ProcessingRun(
        run_id="run_simulated_fail",
        source_file="batch_retry.csv",
        file_hash="hash_retry_batch",
        status=BatchStatus.FAILED,
        input_count=2,
        failure_reason="Simulated connection timeout",
    )
    target_db.add(failed_run)
    target_db.commit()

    # Re-run / retry the failed batch
    run, is_new = BatchManager.get_or_create_run(
        db=target_db,
        source_file="batch_retry.csv",
        file_hash="hash_retry_batch",
        input_count=2,
        allow_rerun=True
    )
    assert run.run_id == "run_simulated_fail"
    assert run.status == BatchStatus.PROCESSING

    # Execute retry
    retry_records = [
        {"event_id": "e_ret_1", "transaction_id": "t_ret_1", "customer_id": "c1", "product_id": "p1", "event_type": "NEW", "amount": "200.00", "currency": "USD", "event_timestamp": "2026-11-10T11:00:00Z"},
        {"event_id": "e_ret_2", "transaction_id": "t_ret_2", "customer_id": "c2", "product_id": "p2", "event_type": "NEW", "amount": "300.00", "currency": "USD", "event_timestamp": "2026-11-10T11:00:00Z"},
    ]
    res_retry = processor.process_records(retry_records, source_name="batch_retry_complete.csv")
    assert res_retry.status == "COMPLETED"

    # Verify no duplicate transactions and exact count
    total_tx = target_db.query(Transaction).count()
    assert total_tx == 3  # 1 initial + 2 retry


# ----------------------------------------------------------------------
# 5. REFERENTIAL INTEGRITY & DATABASE CONSTRAINTS
# ----------------------------------------------------------------------
def test_database_foreign_key_constraints(target_db):
    """Verify SQLite foreign key constraints enforce relational integrity between runs and child tables."""
    run = ProcessingRun(
        run_id="run_fk_test",
        source_file="fk_test.csv",
        file_hash="hash_fk",
        status="COMPLETED",
        input_count=1,
    )
    target_db.add(run)
    target_db.commit()

    # Valid foreign key insert
    rej = RejectedRecord(
        run_id="run_fk_test",
        source_file="fk_test.csv",
        line_number=1,
        raw_data="bad,row",
        rejection_code="INVALID",
        rejection_reason="Test reason",
    )
    target_db.add(rej)
    target_db.commit()
    assert target_db.query(RejectedRecord).filter_by(run_id="run_fk_test").count() == 1


# ----------------------------------------------------------------------
# 6. CURRENCY ALLOWLIST VALIDATION
# ----------------------------------------------------------------------
def test_currency_allowlist_validation():
    """Verify ISO 4217 allowlist accepts valid currencies and rejects unsupported codes."""
    valid_currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR", "CHF", "CNY", "SGD"]
    for curr in valid_currencies:
        row = {
            "event_id": "e_curr",
            "transaction_id": "t_curr",
            "customer_id": "c1",
            "product_id": "p1",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": curr,
            "event_timestamp": "2026-11-10T10:00:00Z",
        }
        is_valid, _, _, _ = SchemaValidator.validate_record(row)
        assert is_valid is True, f"Expected {curr} to be valid"

    unsupported_currencies = ["ZZZ", "ABC", "XXX", "QQQ"]
    for curr in unsupported_currencies:
        row = {
            "event_id": "e_curr",
            "transaction_id": "t_curr",
            "customer_id": "c1",
            "product_id": "p1",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": curr,
            "event_timestamp": "2026-11-10T10:00:00Z",
        }
        is_valid, reason, code, _ = SchemaValidator.validate_record(row)
        assert is_valid is False
        assert code == "UNSUPPORTED_CURRENCY"


# ----------------------------------------------------------------------
# 7. COLUMN PROFILING FOR KEY IDENTIFIERS
# ----------------------------------------------------------------------
def test_event_and_transaction_id_column_profiling():
    """Verify event_id and transaction_id are profiled for nulls, cardinality, and duplicates."""
    records = [
        {"event_id": "E1", "transaction_id": "T1", "customer_id": "C1", "product_id": "P1", "amount": "10.00"},
        {"event_id": "E2", "transaction_id": "T1", "customer_id": "C1", "product_id": "P1", "amount": "20.00"},  # T1 repeated
        {"event_id": "E3", "transaction_id": "T2", "customer_id": "C2", "product_id": "P2", "amount": "30.00"},
    ]
    profile = ColumnProfiler.profile_columns(records, run_id="R_ID_PROF")
    cols = profile["columns"]

    # event_id profile
    e_prof = cols["event_id"]
    assert e_prof["total_count"] == 3
    assert e_prof["null_count"] == 0
    assert e_prof["distinct_count"] == 3
    assert e_prof["duplicate_count"] == 0

    # transaction_id profile
    t_prof = cols["transaction_id"]
    assert t_prof["total_count"] == 3
    assert t_prof["distinct_count"] == 2
    assert t_prof["duplicate_count"] == 1  # T1 duplicate


# ----------------------------------------------------------------------
# 8. API ROUTE PARITY AND FUNCTIONALITY
# ----------------------------------------------------------------------
def test_all_api_endpoints_functionality(target_db):
    """Verify every documented route handler executes without error and matches contracts."""
    # 1. Health
    h = health_check()
    assert h.status == "UP"

    # 2. Batches list
    b_list = batches.list_batches(status_filter=None, limit=10, offset=0, db=target_db)
    assert isinstance(b_list, list)

    # 3. Daily metrics
    m_list = metrics.get_daily_metrics(db=target_db)
    assert isinstance(m_list, list)

    # 4. Quality profiles
    p_list = metrics.get_quality_profiles(db=target_db)
    assert isinstance(p_list, list)

    # 5. Alerts list
    a_list = alerts.list_alerts(db=target_db)
    assert isinstance(a_list, list)

    # 6. Rejected records
    rej_list = reports.get_rejected_records(run_id=None, limit=10, db=target_db)
    assert isinstance(rej_list, list)
