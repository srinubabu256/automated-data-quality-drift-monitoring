"""Adversarial verification script executing 8 critical invariant tests."""
import os
import sys
import uuid
import tempfile
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.models.database_models import (
    Base,
    Transaction,
    TransactionHistory,
    DailyMetric,
    ProcessingRun,
    RawEvent,
    RejectedRecord,
    BaselineProfile,
)
from app.models.enums import EventType, RecordStatus
from app.ingestion.pipeline import IngestionPipeline
from app.processing.transaction_processor import TransactionProcessor
from app.processing.recomputation import RecomputationEngine
from app.reporting.reconciliation import ReconciliationEngine


def main():
    print("=" * 70)
    print("STARTING ADVERSARIAL VERIFICATION SUITE")
    print("=" * 70)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed baseline
    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Adversarial Baseline",
        is_active=True,
        record_volume=1000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        event_freshness_sec=3600.0,
    )
    db.add(baseline)
    db.commit()

    processor = TransactionProcessor(db)

    # -------------------------------------------------------------
    # 1. Transaction updates do not double-count amounts
    # -------------------------------------------------------------
    print("\n[VERIFICATION 1] Testing transaction update amount conservation...")
    events_1 = [
        {
            "event_id": "evt_new_101",
            "transaction_id": "TXN_UPDATE_TEST",
            "customer_id": "CUST_101",
            "product_id": "PROD_101",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
            "source_system": "ERP",
        }
    ]
    res_1 = processor.process_records(events_1, source_name="BATCH_1")

    active_sum_1 = db.query(func.coalesce(func.sum(Transaction.current_amount), Decimal("0.00"))).filter(
        Transaction.status == "ACTIVE"
    ).scalar()
    print(f"  After NEW: Active transaction sum in DB = ${active_sum_1:.2f} (Expected: $100.00)")
    assert active_sum_1 == Decimal("100.00"), f"Expected 100.00, got {active_sum_1}"

    # Now apply UPDATE with $150.00
    events_update = [
        {
            "event_id": "evt_upd_101",
            "transaction_id": "TXN_UPDATE_TEST",
            "customer_id": "CUST_101",
            "product_id": "PROD_101",
            "event_type": "UPDATE",
            "amount": "150.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T11:00:00Z",
            "source_system": "ERP",
        }
    ]
    res_upd = processor.process_records(events_update, source_name="BATCH_2")

    active_sum_2 = db.query(func.coalesce(func.sum(Transaction.current_amount), Decimal("0.00"))).filter(
        Transaction.status == "ACTIVE"
    ).scalar()
    tx_count_2 = db.query(Transaction).filter_by(transaction_id="TXN_UPDATE_TEST").count()
    print(f"  After UPDATE: Active transaction sum in DB = ${active_sum_2:.2f} (Expected: $150.00, NOT $250.00)")
    print(f"  Unique row count for transaction_id = {tx_count_2} (Expected: 1)")
    assert active_sum_2 == Decimal("150.00"), f"Double counting detected! Expected 150.00, got {active_sum_2}"
    assert tx_count_2 == 1, f"Duplicate transaction rows found: {tx_count_2}"
    print("  --> [PASS] Updates do NOT double-count amounts.")

    # -------------------------------------------------------------
    # 2. Reversals correctly reduce active totals
    # -------------------------------------------------------------
    print("\n[VERIFICATION 2] Testing reversal reduction of active totals...")
    events_rev_init = [
        {
            "event_id": "evt_new_201",
            "transaction_id": "TXN_REV_TEST",
            "customer_id": "CUST_201",
            "product_id": "PROD_201",
            "event_type": "NEW",
            "amount": "200.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
            "source_system": "ERP",
        }
    ]
    processor.process_records(events_rev_init, source_name="BATCH_3")

    active_sum_before_rev = db.query(func.coalesce(func.sum(Transaction.current_amount), Decimal("0.00"))).filter(
        Transaction.status == "ACTIVE"
    ).scalar()
    print(f"  Before Reversal: Total Active Sum = ${active_sum_before_rev:.2f} ($150 + $200 = $350)")
    assert active_sum_before_rev == Decimal("350.00")

    # Perform REVERSAL on TXN_REV_TEST
    events_reversal = [
        {
            "event_id": "evt_rev_201",
            "transaction_id": "TXN_REV_TEST",
            "customer_id": "CUST_201",
            "product_id": "PROD_201",
            "event_type": "REVERSAL",
            "amount": "200.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T12:00:00Z",
            "source_system": "ERP",
        }
    ]
    processor.process_records(events_reversal, source_name="BATCH_4")

    active_sum_after_rev = db.query(func.coalesce(func.sum(Transaction.current_amount), Decimal("0.00"))).filter(
        Transaction.status == "ACTIVE"
    ).scalar()
    rev_tx = db.query(Transaction).filter_by(transaction_id="TXN_REV_TEST").first()
    print(f"  After Reversal: Total Active Sum = ${active_sum_after_rev:.2f} (Expected: $150.00)")
    print(f"  TXN_REV_TEST Status = '{rev_tx.status}', is_reversed = {rev_tx.is_reversed}, Current Amount = ${rev_tx.current_amount:.2f}")
    assert active_sum_after_rev == Decimal("150.00")
    assert rev_tx.status == "REVERSED"
    assert rev_tx.current_amount == Decimal("0.00")
    print("  --> [PASS] Reversals correctly reduce active totals to $0.00.")

    # -------------------------------------------------------------
    # 3. Repeated reversals are rejected
    # -------------------------------------------------------------
    print("\n[VERIFICATION 3] Testing repeated reversal rejection...")
    events_repeat_rev = [
        {
            "event_id": "evt_rev_repeat_202",
            "transaction_id": "TXN_REV_TEST",
            "customer_id": "CUST_201",
            "product_id": "PROD_201",
            "event_type": "REVERSAL",
            "amount": "200.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T13:00:00Z",
            "source_system": "ERP",
        }
    ]
    res_repeat = processor.process_records(events_repeat_rev, source_name="BATCH_5")

    # Check that transaction remains reversed at 0.00
    rev_tx_check = db.query(Transaction).filter_by(transaction_id="TXN_REV_TEST").first()
    assert rev_tx_check.is_reversed is True
    assert rev_tx_check.current_amount == Decimal("0.00")

    # Check transaction history records REVERSAL_DUPLICATE_IGNORED
    dup_hist = db.query(TransactionHistory).filter_by(
        transaction_id="TXN_REV_TEST",
        event_type="REVERSAL_DUPLICATE_IGNORED"
    ).first()
    assert dup_hist is not None, "Repeated reversal was not flagged as duplicate ignored"
    print(f"  Duplicate Reversal Audited: event_type='{dup_hist.event_type}', amount=${dup_hist.new_amount:.2f}")

    # Active sum must still be $150.00 (not subtracted again)
    active_sum_check = db.query(func.coalesce(func.sum(Transaction.current_amount), Decimal("0.00"))).filter(
        Transaction.status == "ACTIVE"
    ).scalar()
    print(f"  Active Sum after repeat reversal attempt = ${active_sum_check:.2f} (Expected: $150.00, NOT $0 or negative)")
    assert active_sum_check == Decimal("150.00")
    print("  --> [PASS] Repeated reversals are strictly rejected from modifying state, preventing double deduction.")

    # -------------------------------------------------------------
    # 4. Late events recompute historical daily metrics correctly
    # -------------------------------------------------------------
    print("\n[VERIFICATION 4] Testing late events and historical metric recomputation...")
    date_hist = datetime(2026, 10, 15, tzinfo=timezone.utc).date()

    # Initial transaction on 2026-10-15 ($50.00)
    tx_init = Transaction(
        transaction_id="TXN_LATE_1",
        customer_id="CUST_LATE",
        product_id="PROD_LATE",
        current_amount=Decimal("50.00"),
        currency="USD",
        status="ACTIVE",
        is_reversed=False,
        latest_event_id="evt_init_1",
        last_run_id="run_init",
        first_event_timestamp=datetime(2026, 10, 15, 9, 0, 0, tzinfo=timezone.utc),
        latest_event_timestamp=datetime(2026, 10, 15, 9, 0, 0, tzinfo=timezone.utc),
        version=1,
    )
    db.add(tx_init)
    db.commit()

    RecomputationEngine.recompute_dates(db, [date_hist])
    db.commit()

    m_before = db.query(DailyMetric).filter_by(metric_date=date_hist).first()
    print(f"  Initial Daily Metric for {date_hist}: ${float(m_before.total_amount):.2f} (count={m_before.total_transactions})")
    assert float(m_before.total_amount) == 50.0
    assert m_before.total_transactions == 1

    # Late event arriving for 2026-10-15 ($75.00)
    tx_late = Transaction(
        transaction_id="TXN_LATE_2",
        customer_id="CUST_LATE_2",
        product_id="PROD_LATE_2",
        current_amount=Decimal("75.00"),
        currency="USD",
        status="ACTIVE",
        is_reversed=False,
        latest_event_id="evt_late_2",
        last_run_id="run_late",
        first_event_timestamp=datetime(2026, 10, 15, 14, 0, 0, tzinfo=timezone.utc),
        latest_event_timestamp=datetime(2026, 10, 15, 14, 0, 0, tzinfo=timezone.utc),
        version=1,
    )
    db.add(tx_late)
    db.commit()

    # Trigger recomputation on historical date
    affected = RecomputationEngine.recompute_dates(db, [date_hist])
    db.commit()

    m_after = db.query(DailyMetric).filter_by(metric_date=date_hist).first()
    print(f"  After Late Event: Daily Metric for {date_hist} recomputed to ${float(m_after.total_amount):.2f} (count={m_after.total_transactions})")
    assert float(m_after.total_amount) == 125.0
    assert m_after.total_transactions == 2
    print("  --> [PASS] Late-arriving events accurately recompute historical daily metrics.")

    # -------------------------------------------------------------
    # 5. Rerunning the same CSV does not duplicate transactions
    # -------------------------------------------------------------
    print("\n[VERIFICATION 5] Testing rerun idempotency on identical CSV payload...")
    from app.ingestion.batch_manager import DuplicateFileError
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
        tmp.write("event_id,transaction_id,customer_id,product_id,event_type,amount,currency,event_timestamp\n")
        tmp.write("evt_idem_1,TXN_IDEM_1,CUST_001,PROD_001,NEW,300.00,USD,2026-11-10T12:00:00Z\n")
        tmp.write("evt_idem_2,TXN_IDEM_2,CUST_002,PROD_002,NEW,400.00,USD,2026-11-10T12:05:00Z\n")
        tmp_path = tmp.name

    try:
        # First execution
        first_result = processor.process_file(Path(tmp_path), allow_rerun=False)
        print(f"  First Run: status='{first_result.status}', input={first_result.input_count}, accepted={first_result.accepted_count}")
        assert first_result.status in ["COMPLETED", "SUCCESS"]
        assert first_result.accepted_count == 2

        count_after_first = db.query(Transaction).filter(Transaction.transaction_id.in_(["TXN_IDEM_1", "TXN_IDEM_2"])).count()
        assert count_after_first == 2

        # Second execution (identical file) must be blocked via DuplicateFileError
        duplicate_caught = False
        try:
            processor.process_file(Path(tmp_path), allow_rerun=False)
        except DuplicateFileError as e:
            duplicate_caught = True
            print(f"  Second Run: Successfully caught DuplicateFileError for file_hash '{e.file_hash[:16]}...'")

        assert duplicate_caught is True, "Expected DuplicateFileError on re-run of identical file"

        count_after_second = db.query(Transaction).filter(Transaction.transaction_id.in_(["TXN_IDEM_1", "TXN_IDEM_2"])).count()
        print(f"  Transaction row count in DB after re-run: {count_after_second} (Expected: 2, NOT 4)")
        assert count_after_second == 2
        print("  --> [PASS] Idempotent ingestion detects identical file hash and prevents duplicate insertion.")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    # -------------------------------------------------------------
    # 6. Bulk database persistence preserves transaction history
    # -------------------------------------------------------------
    print("\n[VERIFICATION 6] Testing bulk database persistence and audit history links...")
    history_records = db.query(TransactionHistory).filter_by(transaction_id="TXN_UPDATE_TEST").order_by(TransactionHistory.id.asc()).all()
    print(f"  Audit versions found for 'TXN_UPDATE_TEST': {len(history_records)}")
    for h in history_records:
        print(f"    History ID {h.id}: Event='{h.event_type}', New Amount=${float(h.new_amount):.2f}, Timestamp={h.event_timestamp}")
    assert len(history_records) >= 2
    assert history_records[0].event_type == "NEW" and history_records[0].new_amount == Decimal("100.00")
    assert history_records[1].event_type == "UPDATE" and history_records[1].new_amount == Decimal("150.00")
    print("  --> [PASS] Versioned transaction history and audit links are strictly preserved.")

    # -------------------------------------------------------------
    # 7. Reconciliation detects intentionally introduced discrepancies
    # -------------------------------------------------------------
    print("\n[VERIFICATION 7] Testing reconciliation discrepancy detection...")
    run_tampered = ProcessingRun(
        run_id="run_tampered_01",
        source_file="tampered.csv",
        file_hash="hash_tampered",
        status="SUCCESS",
        input_count=100,      # Header claims 100
        accepted_count=80,     # 80 accepted
        rejected_count=10,     # 10 rejected
        duplicate_count=5,     # 5 duplicates => Total = 95 != 100
        processed_count=80,
    )
    db.add(run_tampered)
    db.commit()

    recon_tampered = ReconciliationEngine.verify_run_reconciliation(db, "run_tampered_01")
    print(f"  Tampered Run Equation: {recon_tampered['equation']}")
    print(f"  Reconciliation Status: '{recon_tampered['status']}', Reconciled={recon_tampered['reconciled']}")
    print(f"  Discrepancy: {recon_tampered['counts']['discrepancy']} records")
    assert recon_tampered["status"] == "DISCREPANCY"
    assert recon_tampered["reconciled"] is False
    assert recon_tampered["counts"]["discrepancy"] == 5

    # Test balanced run
    recon_balanced = ReconciliationEngine.verify_run_reconciliation(db, res_1.run_id)
    print(f"  Valid Run Status: '{recon_balanced['status']}', Reconciled={recon_balanced['reconciled']}")
    assert recon_balanced["status"] == "BALANCED"
    assert recon_balanced["reconciled"] is True
    print("  --> [PASS] Reconciliation engine rigorously flags discrepancies when equations do not balance.")

    # -------------------------------------------------------------
    # 8. API results change correctly when different datasets are uploaded
    # -------------------------------------------------------------
    print("\n[VERIFICATION 8] Testing dynamic metric updates across different datasets...")
    from app.api.routes.metrics import get_daily_metrics

    # Check metrics for 2026-10-15
    res_m1 = get_daily_metrics(
        start_date=date_hist,
        end_date=date_hist,
        db=db
    )
    initial_total = float(res_m1[0].total_amount) if res_m1 else 0.0
    print(f"  Initial API Metric Total for 2026-10-15 = ${initial_total:.2f}")

    # Add another distinct transaction on 2026-10-15 ($250.00)
    tx_diff = Transaction(
        transaction_id="TXN_DATASET_B",
        customer_id="CUST_DATASET_B",
        product_id="PROD_DATASET_B",
        current_amount=Decimal("250.00"),
        currency="USD",
        status="ACTIVE",
        is_reversed=False,
        latest_event_id="evt_dataset_b",
        last_run_id="run_b",
        first_event_timestamp=datetime(2026, 10, 15, 18, 0, 0, tzinfo=timezone.utc),
        latest_event_timestamp=datetime(2026, 10, 15, 18, 0, 0, tzinfo=timezone.utc),
        version=1,
    )
    db.add(tx_diff)
    db.commit()
    RecomputationEngine.recompute_dates(db, [date_hist])
    db.commit()

    res_m2 = get_daily_metrics(
        start_date=date_hist,
        end_date=date_hist,
        db=db
    )
    updated_total = float(res_m2[0].total_amount)
    print(f"  Updated API Metric Total for 2026-10-15 = ${updated_total:.2f} (Expected: ${initial_total + 250:.2f})")
    assert updated_total == initial_total + 250.0
    print("  --> [PASS] API outputs dynamically and truthfully reflect newly ingested data.")

    print("\n" + "=" * 70)
    print("ALL 8 ADVERSARIAL VERIFICATIONS PASSED WITH ZERO FAILURES!")
    print("=" * 70)


if __name__ == "__main__":
    main()
