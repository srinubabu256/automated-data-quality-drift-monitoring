"""Tests for transaction reversals and double-reversal prevention."""
from decimal import Decimal
from datetime import date
from app.processing.transaction_processor import TransactionProcessor
from app.models.database_models import Transaction, DailyMetric


def test_transaction_reversal(test_db):
    """Verify REVERSAL marks transaction reversed and sets current amount contribution to 0."""
    processor = TransactionProcessor(db=test_db)
    records = [
        {
            "event_id": "evt_rev_01",
            "transaction_id": "TXN_REV_1",
            "customer_id": "CUST_REV_1",
            "product_id": "PROD_REV_1",
            "event_type": "NEW",
            "amount": "500.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        },
        {
            "event_id": "evt_rev_02",
            "transaction_id": "TXN_REV_1",
            "customer_id": "CUST_REV_1",
            "product_id": "PROD_REV_1",
            "event_type": "REVERSAL",
            "amount": "500.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T11:00:00Z",
        }
    ]
    res = processor.process_records(records, source_name="test_reversal")
    assert res.accepted_count == 2
    assert res.processed_count == 2

    tx = test_db.query(Transaction).filter_by(transaction_id="TXN_REV_1").first()
    assert tx.is_reversed is True
    assert tx.status == "REVERSED"
    assert tx.current_amount == Decimal("0.00")

    # Check daily metrics: total active transactions on 2026-11-10 should be 0, total amount 0
    metric = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 10)).first()
    assert metric is not None
    assert metric.total_transactions == 0
    assert metric.total_amount == Decimal("0.00")


def test_duplicate_reversal_prevention(test_db):
    """Verify duplicate reversal does not cause double deductions or errors."""
    processor = TransactionProcessor(db=test_db)
    batch_1 = [
        {
            "event_id": "evt_rev_dup_01",
            "transaction_id": "TXN_REV_2",
            "customer_id": "CUST_REV_2",
            "product_id": "PROD_REV_2",
            "event_type": "NEW",
            "amount": "300.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T09:00:00Z",
        },
        {
            "event_id": "evt_rev_dup_02",
            "transaction_id": "TXN_REV_2",
            "customer_id": "CUST_REV_2",
            "product_id": "PROD_REV_2",
            "event_type": "REVERSAL",
            "amount": "300.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        }
    ]
    processor.process_records(batch_1, source_name="b1")

    # Second reversal for the same transaction
    batch_2 = [
        {
            "event_id": "evt_rev_dup_03",
            "transaction_id": "TXN_REV_2",
            "customer_id": "CUST_REV_2",
            "product_id": "PROD_REV_2",
            "event_type": "REVERSAL",
            "amount": "300.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T12:00:00Z",
        }
    ]
    processor.process_records(batch_2, source_name="b2")

    tx = test_db.query(Transaction).filter_by(transaction_id="TXN_REV_2").first()
    assert tx.is_reversed is True
    assert tx.current_amount == Decimal("0.00")

    metric = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 10)).first()
    assert metric.total_amount == Decimal("0.00")

