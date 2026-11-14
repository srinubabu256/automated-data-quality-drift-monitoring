"""Tests for NEW transaction creation, duplicate event handling, updates, and out-of-order resolution."""
from decimal import Decimal
from app.processing.transaction_processor import TransactionProcessor
from app.models.database_models import Transaction, TransactionHistory, RawEvent


def test_new_transaction_creation(test_db):
    """Verify NEW transaction creates active record and logs history."""
    processor = TransactionProcessor(db=test_db)
    records = [
        {
            "event_id": "evt_tx_01",
            "transaction_id": "TXN_001",
            "customer_id": "CUST_001",
            "product_id": "PROD_001",
            "event_type": "NEW",
            "amount": "120.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
            "source_system": "WEB_STORE"
        }
    ]
    res = processor.process_records(records, source_name="test_new")
    assert res.accepted_count == 1
    assert res.processed_count == 1
    assert res.reconciliation_passed is True

    tx = test_db.query(Transaction).filter_by(transaction_id="TXN_001").first()
    assert tx is not None
    assert tx.current_amount == Decimal("120.00")
    assert tx.status == "ACTIVE"
    assert tx.is_reversed is False
    assert tx.version == 1

    hist = test_db.query(TransactionHistory).filter_by(transaction_id="TXN_001").all()
    assert len(hist) == 1
    assert hist[0].event_type == "NEW"


def test_duplicate_event_id_deduplication(test_db):
    """Verify exact duplicate event_id is rejected/deduped and does not double-count."""
    processor = TransactionProcessor(db=test_db)
    records = [
        {
            "event_id": "evt_dup_01",
            "transaction_id": "TXN_002",
            "customer_id": "CUST_002",
            "product_id": "PROD_002",
            "event_type": "NEW",
            "amount": "200.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T11:00:00Z",
            "source_system": "WEB_STORE"
        },
        {
            "event_id": "evt_dup_01",  # Same event_id
            "transaction_id": "TXN_002",
            "customer_id": "CUST_002",
            "product_id": "PROD_002",
            "event_type": "NEW",
            "amount": "200.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T11:00:00Z",
            "source_system": "WEB_STORE"
        }
    ]
    res = processor.process_records(records, source_name="test_dup")
    assert res.input_count == 2
    assert res.accepted_count == 1
    assert res.duplicate_count == 1
    assert res.reconciliation_passed is True

    # Check only one transaction created
    tx_count = test_db.query(Transaction).filter_by(transaction_id="TXN_002").count()
    assert tx_count == 1


def test_transaction_update_lifecycle(test_db):
    """Verify UPDATE alters current amount and version without creating a second transaction."""
    processor = TransactionProcessor(db=test_db)
    records = [
        {
            "event_id": "evt_u_01",
            "transaction_id": "TXN_003",
            "customer_id": "CUST_003",
            "product_id": "PROD_003",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        },
        {
            "event_id": "evt_u_02",
            "transaction_id": "TXN_003",
            "customer_id": "CUST_003",
            "product_id": "PROD_003",
            "event_type": "UPDATE",
            "amount": "175.50",
            "currency": "USD",
            "event_timestamp": "2026-11-10T11:00:00Z",
        }
    ]
    res = processor.process_records(records, source_name="test_update")
    assert res.accepted_count == 2
    assert res.processed_count == 2

    tx_list = test_db.query(Transaction).filter_by(transaction_id="TXN_003").all()
    assert len(tx_list) == 1
    tx = tx_list[0]
    assert tx.current_amount == Decimal("175.50")
    assert tx.version == 2

    # Verify history has 2 entries (NEW then UPDATE)
    hist = test_db.query(TransactionHistory).filter_by(transaction_id="TXN_003").order_by(TransactionHistory.applied_at).all()
    assert len(hist) == 2
    assert hist[0].event_type == "NEW"
    assert hist[0].new_amount == Decimal("100.00")
    assert hist[1].event_type == "UPDATE"
    assert hist[1].previous_amount == Decimal("100.00")
    assert hist[1].new_amount == Decimal("175.50")


def test_out_of_order_event_resolution(test_db):
    """Verify an older event arriving after a newer state does not downgrade transaction amount."""
    processor = TransactionProcessor(db=test_db)

    # First apply a newer update: 12:00:00
    batch_1 = [
        {
            "event_id": "evt_oo_01",
            "transaction_id": "TXN_004",
            "customer_id": "CUST_004",
            "product_id": "PROD_004",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        },
        {
            "event_id": "evt_oo_02",
            "transaction_id": "TXN_004",
            "customer_id": "CUST_004",
            "product_id": "PROD_004",
            "event_type": "UPDATE",
            "amount": "300.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T12:00:00Z",
        }
    ]
    processor.process_records(batch_1, source_name="b1")

    # Now an out-of-order event arrives with timestamp 11:00:00 (older than 12:00:00)
    batch_2 = [
        {
            "event_id": "evt_oo_03",
            "transaction_id": "TXN_004",
            "customer_id": "CUST_004",
            "product_id": "PROD_004",
            "event_type": "UPDATE",
            "amount": "150.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T11:00:00Z",
        }
    ]
    processor.process_records(batch_2, source_name="b2")

    tx = test_db.query(Transaction).filter_by(transaction_id="TXN_004").first()
    # Amount must remain 300.00 (newer valid state preserved)
    assert tx.current_amount == Decimal("300.00")
    assert tx.version == 2

