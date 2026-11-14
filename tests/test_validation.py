"""Tests for schema validation, data types, reference integrity, and quarantine."""
from decimal import Decimal
from app.validation.schema_validator import SchemaValidator
from app.validation.business_validator import BusinessValidator
from app.validation.quarantine import QuarantineManager


def test_schema_validator_valid_record():
    """Verify validation passes for standard valid record."""
    row = {
        "event_id": "evt_101",
        "transaction_id": "TXN_101",
        "customer_id": "CUST_001",
        "product_id": "PROD_001",
        "event_type": "NEW",
        "amount": "150.75",
        "currency": "USD",
        "event_timestamp": "2026-11-10T12:00:00Z",
    }
    is_valid, reason, code, val_data = SchemaValidator.validate_record(row)
    assert is_valid is True
    assert reason is None
    assert val_data["amount"] == Decimal("150.75")
    assert val_data["event_timestamp"].year == 2026


def test_schema_validator_missing_required_fields():
    """Verify missing required fields fail validation."""
    row = {
        "event_id": "",
        "transaction_id": "TXN_101",
        "customer_id": "CUST_001",
        "product_id": "PROD_001",
        "event_type": "NEW",
        "amount": "150.75",
        "event_timestamp": "2026-11-10T12:00:00Z",
    }
    is_valid, reason, code, val_data = SchemaValidator.validate_record(row)
    assert is_valid is False
    assert code == "MISSING_REQUIRED_FIELD"


def test_schema_validator_invalid_amount_types():
    """Verify non-numeric and negative amounts fail validation."""
    bad_amounts = ["-10.00", "0.00", "abc", "N/A", "--5"]
    for amt in bad_amounts:
        row = {
            "event_id": "evt_test",
            "transaction_id": "TXN_test",
            "customer_id": "CUST_001",
            "product_id": "PROD_001",
            "event_type": "NEW",
            "amount": amt,
            "event_timestamp": "2026-11-10T12:00:00Z",
        }
        is_valid, reason, code, _ = SchemaValidator.validate_record(row)
        assert is_valid is False
        assert code in ["INVALID_AMOUNT_VALUE", "MALFORMED_AMOUNT_TYPE"]


def test_schema_validator_malformed_timestamp():
    """Verify malformed timestamps fail validation."""
    bad_timestamps = ["2026-99-99 25:99:99", "INVALID_DATE", "not-a-date", "2026/13/45"]
    for ts in bad_timestamps:
        row = {
            "event_id": "evt_test",
            "transaction_id": "TXN_test",
            "customer_id": "CUST_001",
            "product_id": "PROD_001",
            "event_type": "NEW",
            "amount": "100.00",
            "event_timestamp": ts,
        }
        is_valid, reason, code, _ = SchemaValidator.validate_record(row)
        assert is_valid is False
        assert code == "MALFORMED_TIMESTAMP"


def test_business_validator_invalid_references():
    """Verify invalid customer and product reference keys are rejected."""
    bad_data = {
        "customer_id": "INV_CUST_@@@",
        "product_id": "PROD_001",
        "transaction_id": "TXN_001",
    }
    is_valid, reason, code = BusinessValidator.validate_reference_keys(bad_data)
    assert is_valid is False
    assert code == "INVALID_CUSTOMER_KEY"


def test_quarantine_manager_stores_and_retrieves(test_db):
    """Verify rejected records are safely stored in DB and queryable with line numbers."""
    rejected_items = [
        {
            "line_number": 4,
            "raw_data": {"event_id": "bad_1", "amount": "-50.00"},
            "reason": "Invalid amount",
            "code": "INVALID_AMOUNT_VALUE",
        },
        {
            "line_number": 12,
            "raw_data": {"event_id": "bad_2", "event_timestamp": "bad_date"},
            "reason": "Malformed timestamp",
            "code": "MALFORMED_TIMESTAMP",
        }
    ]
    # Create run first
    from app.models.database_models import ProcessingRun
    run = ProcessingRun(
        run_id="run_test_quarantine",
        source_file="test.csv",
        file_hash="h123",
        status="PROCESSING",
        input_count=2
    )
    test_db.add(run)
    test_db.commit()

    count = QuarantineManager.quarantine_records(
        db=test_db,
        run_id="run_test_quarantine",
        source_file="test.csv",
        rejected_items=rejected_items
    )
    assert count == 2

    stored = QuarantineManager.get_rejected_records(test_db, run_id="run_test_quarantine")
    assert len(stored) == 2
    assert stored[0].line_number in [4, 12]
    assert stored[0].rejection_code in ["INVALID_AMOUNT_VALUE", "MALFORMED_TIMESTAMP"]

