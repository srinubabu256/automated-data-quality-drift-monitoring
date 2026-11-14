"""Comprehensive test suite for the 10 Required Negative Scenarios."""
import io
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database_models import Base, Transaction, ProcessingRun, RejectedRecord, DailyMetric
from app.processing.transaction_processor import TransactionProcessor
from app.ingestion.batch_manager import DuplicateFileError
from app.validation.schema_validator import SchemaValidator
from app.validation.business_validator import BusinessValidator
from app.processing.recomputation import RecomputationEngine


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# Scenario 1: Malformed Input
def test_scenario_1_malformed_input():
    """Verify malformed amounts, timestamps, and invalid non-numeric inputs fail validation."""
    malformed_rows = [
        {"event_id": "e1", "transaction_id": "t1", "customer_id": "c1", "product_id": "p1", "event_type": "NEW", "amount": "INVALID_AMOUNT", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"},
        {"event_id": "e2", "transaction_id": "t2", "customer_id": "c2", "product_id": "p2", "event_type": "NEW", "amount": "100.00", "currency": "USD", "event_timestamp": "NOT_A_TIMESTAMP"},
        {"event_id": "e3", "transaction_id": "t3", "customer_id": "c3", "product_id": "p3", "event_type": "NEW", "amount": "-50.00", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"},
    ]
    for row in malformed_rows:
        is_valid, reason, code, _ = SchemaValidator.validate_record(row)
        assert is_valid is False
        assert code in ["MALFORMED_AMOUNT_TYPE", "MALFORMED_TIMESTAMP", "INVALID_AMOUNT_VALUE"]


# Scenario 2: Missing Required Field
def test_scenario_2_missing_required_field():
    """Verify records missing required columns fail validation with MISSING_REQUIRED_FIELD."""
    required_fields = ["event_id", "transaction_id", "customer_id", "product_id", "event_type", "amount", "event_timestamp"]
    for field in required_fields:
        row = {
            "event_id": "e_req",
            "transaction_id": "t_req",
            "customer_id": "c_req",
            "product_id": "p_req",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        }
        del row[field]
        is_valid, reason, code, _ = SchemaValidator.validate_record(row)
        assert is_valid is False
        assert code == "MISSING_REQUIRED_FIELD"


# Scenario 3: Duplicate Key or Event
def test_scenario_3_duplicate_key_or_event(test_db):
    """Verify duplicate event IDs are quarantined and do not cause double processing."""
    processor = TransactionProcessor(db=test_db)
    batch = [
        {"event_id": "evt_dup_key_1", "transaction_id": "TXN_DUP_1", "customer_id": "CUST_1", "product_id": "PROD_1", "event_type": "NEW", "amount": "100.00", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"},
        {"event_id": "evt_dup_key_1", "transaction_id": "TXN_DUP_2", "customer_id": "CUST_2", "product_id": "PROD_2", "event_type": "NEW", "amount": "200.00", "currency": "USD", "event_timestamp": "2026-11-10T10:05:00Z"},
    ]
    res = processor.process_records(batch, source_name="dup_test.csv")
    assert res.accepted_count == 1
    assert res.duplicate_count == 1
    assert test_db.query(Transaction).count() == 1


# Scenario 4: Unexpected Schema Change
def test_scenario_4_unexpected_schema_change():
    """Verify schema validator detects missing critical columns or malformed dictionaries."""
    empty_dict = {}
    is_valid, reason, code, _ = SchemaValidator.validate_record(empty_dict)
    assert is_valid is False
    assert code == "MISSING_REQUIRED_FIELD"


# Scenario 5: Empty Batch
def test_scenario_5_empty_batch(test_db):
    """Verify processing an empty batch completes safely and yields balanced reconciliation."""
    processor = TransactionProcessor(db=test_db)
    res = processor.process_records([], source_name="empty_batch.csv")
    assert res.status == "COMPLETED"
    assert res.input_count == 0
    assert res.accepted_count == 0
    assert res.reconciliation_passed is True


# Scenario 6: Partial Failure and Retry
def test_scenario_6_partial_failure_and_retry(test_db):
    """Verify pipeline isolates and quarantines corrupt records while committing valid transactions."""
    processor = TransactionProcessor(db=test_db)
    mixed_batch = [
        {"event_id": "evt_mix_1", "transaction_id": "TXN_MIX_1", "customer_id": "CUST_1", "product_id": "PROD_1", "event_type": "NEW", "amount": "150.00", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"},
        {"event_id": "evt_mix_corrupt", "transaction_id": "TXN_MIX_CORRUPT", "customer_id": "CUST_BAD", "product_id": "PROD_BAD", "event_type": "NEW", "amount": "-99.00", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"},
        {"event_id": "evt_mix_2", "transaction_id": "TXN_MIX_2", "customer_id": "CUST_2", "product_id": "PROD_2", "event_type": "NEW", "amount": "250.00", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"},
    ]
    res = processor.process_records(mixed_batch, source_name="mixed_batch.csv")
    assert res.input_count == 3
    assert res.accepted_count == 2
    assert res.rejected_count == 1
    assert test_db.query(Transaction).count() == 2
    assert test_db.query(RejectedRecord).count() == 1


# Scenario 7: Late-Arriving Event
def test_scenario_7_late_arriving_event(test_db):
    """Verify late-arriving events trigger selective historical metric recomputation."""
    processor = TransactionProcessor(db=test_db)
    # Day 1 event
    batch_day1 = [
        {"event_id": "evt_day1", "transaction_id": "TXN_DAY1", "customer_id": "CUST_1", "product_id": "PROD_1", "event_type": "NEW", "amount": "100.00", "currency": "USD", "event_timestamp": "2026-10-01T12:00:00Z"}
    ]
    processor.process_records(batch_day1, source_name="day1.csv")

    # Day 2 event
    batch_day2 = [
        {"event_id": "evt_day2", "transaction_id": "TXN_DAY2", "customer_id": "CUST_2", "product_id": "PROD_2", "event_type": "NEW", "amount": "200.00", "currency": "USD", "event_timestamp": "2026-10-02T12:00:00Z"}
    ]
    processor.process_records(batch_day2, source_name="day2.csv")

    # Late event for Day 1
    batch_late = [
        {"event_id": "evt_late_day1", "transaction_id": "TXN_DAY1_LATE", "customer_id": "CUST_3", "product_id": "PROD_3", "event_type": "NEW", "amount": "50.00", "currency": "USD", "event_timestamp": "2026-10-01T15:00:00Z"}
    ]
    processor.process_records(batch_late, source_name="late.csv")

    m_day1 = test_db.query(DailyMetric).filter_by(metric_date=datetime(2026, 10, 1).date()).first()
    assert float(m_day1.total_amount) == 150.0
    assert m_day1.total_transactions == 2


# Scenario 8: Out-of-Order Event
def test_scenario_8_out_of_order_event(test_db):
    """Verify older update arriving after a newer update is logged to history without overwriting newer state."""
    processor = TransactionProcessor(db=test_db)
    # 1. NEW at 10:00
    processor.process_records([
        {"event_id": "evt_ord_1", "transaction_id": "TXN_ORD_1", "customer_id": "CUST_1", "product_id": "PROD_1", "event_type": "NEW", "amount": "100.00", "currency": "USD", "event_timestamp": "2026-11-10T10:00:00Z"}
    ], source_name="s1")

    # 2. UPDATE at 12:00 with $300
    processor.process_records([
        {"event_id": "evt_ord_2", "transaction_id": "TXN_ORD_1", "customer_id": "CUST_1", "product_id": "PROD_1", "event_type": "UPDATE", "amount": "300.00", "currency": "USD", "event_timestamp": "2026-11-10T12:00:00Z"}
    ], source_name="s2")

    # 3. OUT-OF-ORDER UPDATE at 11:00 with $200 (older than 12:00)
    processor.process_records([
        {"event_id": "evt_ord_3", "transaction_id": "TXN_ORD_1", "customer_id": "CUST_1", "product_id": "PROD_1", "event_type": "UPDATE", "amount": "200.00", "currency": "USD", "event_timestamp": "2026-11-10T11:00:00Z"}
    ], source_name="s3")

    tx = test_db.query(Transaction).filter_by(transaction_id="TXN_ORD_1").first()
    assert tx.current_amount == Decimal("300.00")


# Scenario 9: Invalid Reference Key
def test_scenario_9_invalid_reference_key():
    """Verify reference keys with prohibited injection characters, NULL, or NONE tokens are rejected."""
    bad_keys = ["CUST_!@#$", "CUST_<script>", "PROD_DROP_TABLE;--", "CUST_NULL", "PROD_NONE"]
    for key in bad_keys:
        data = {"customer_id": key, "product_id": "PROD_VALID", "transaction_id": "TXN_VALID"}
        is_valid, reason, code = BusinessValidator.validate_reference_keys(data)
        assert is_valid is False


# Scenario 10: Rerunning the Same Input
def test_scenario_10_rerunning_same_input(test_db, tmp_path):
    """Verify rerunning identical file raises DuplicateFileError and maintains record count."""
    csv_file = tmp_path / "idempotent_test.csv"
    csv_file.write_text(
        "event_id,transaction_id,customer_id,product_id,event_type,amount,currency,event_timestamp\n"
        "evt_scen10_1,TXN_SCEN10_1,CUST_1,PROD_1,NEW,100.00,USD,2026-11-10T10:00:00Z\n",
        encoding="utf-8"
    )

    processor = TransactionProcessor(db=test_db)
    res1 = processor.process_file(csv_file, allow_rerun=False)
    assert res1.accepted_count == 1

    with pytest.raises(DuplicateFileError):
        processor.process_file(csv_file, allow_rerun=False)

    tx_count = test_db.query(Transaction).filter_by(transaction_id="TXN_SCEN10_1").count()
    assert tx_count == 1
