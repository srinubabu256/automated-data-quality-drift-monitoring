"""Tests for idempotency, same-file reruns, retry recovery, and reconciliation."""
import pytest
from app.processing.transaction_processor import TransactionProcessor
from app.ingestion.batch_manager import DuplicateFileError
from app.reporting.reconciliation import ReconciliationChecker
from app.models.database_models import Transaction, ProcessingRun


def test_same_file_rerun_detection(test_db, tmp_path):
    """Verify rerunning identical file raises DuplicateFileError unless explicit rerun allowed."""
    csv_file = tmp_path / "idempotent_batch.csv"
    csv_file.write_text(
        "event_id,transaction_id,customer_id,product_id,event_type,amount,currency,event_timestamp\n"
        "evt_idem_1,TXN_IDEM_1,CUST_1,PROD_1,NEW,100.00,USD,2026-11-10T10:00:00Z\n",
        encoding="utf-8"
    )

    processor = TransactionProcessor(db=test_db)
    # First execution succeeds
    res1 = processor.process_file(csv_file, allow_rerun=False)
    assert res1.accepted_count == 1

    # Second execution without allow_rerun raises DuplicateFileError
    with pytest.raises(DuplicateFileError):
        processor.process_file(csv_file, allow_rerun=False)

    # Verify no duplicate transaction created
    tx_count = test_db.query(Transaction).filter_by(transaction_id="TXN_IDEM_1").count()
    assert tx_count == 1


def test_terminal_reconciliation_check(test_db):
    """Verify reconciliation check enforces input = accepted + rejected + duplicate."""
    processor = TransactionProcessor(db=test_db)
    records = [
        # 1 valid NEW
        {
            "event_id": "evt_rec_1",
            "transaction_id": "TXN_REC_1",
            "customer_id": "CUST_1",
            "product_id": "PROD_1",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        },
        # 1 duplicate event
        {
            "event_id": "evt_rec_1",
            "transaction_id": "TXN_REC_1",
            "customer_id": "CUST_1",
            "product_id": "PROD_1",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        },
        # 1 invalid record (malformed amount)
        {
            "event_id": "evt_rec_3",
            "transaction_id": "TXN_REC_3",
            "customer_id": "CUST_1",
            "product_id": "PROD_1",
            "event_type": "NEW",
            "amount": "-50.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        }
    ]
    res = processor.process_records(records, source_name="recon_test")
    assert res.input_count == 3
    assert res.accepted_count == 1
    assert res.duplicate_count == 1
    assert res.rejected_count == 1
    assert res.reconciliation_passed is True

    audit = ReconciliationChecker.verify_run_reconciliation(test_db, res.run_id)
    assert audit["reconciled"] is True
    assert audit["status"] in ["SUCCESS", "BALANCED"]
    assert audit["counts"]["discrepancy"] == 0
