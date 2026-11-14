"""Main Transaction Processor coordinating validation, lifecycle, recomputation, and idempotency."""
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from app.ingestion.loader import load_csv, compute_file_hash
from app.ingestion.batch_manager import BatchManager, DuplicateFileError
from app.validation.schema_validator import SchemaValidator
from app.validation.business_validator import BusinessValidator
from app.validation.quarantine import QuarantineManager
from app.processing.update_handler import UpdateHandler
from app.processing.reversal_handler import ReversalHandler
from app.processing.recomputation import RecomputationEngine
from app.models.database_models import (
    ProcessingRun,
    RawEvent,
    Transaction,
    TransactionHistory,
)
from app.models.enums import EventType, RecordStatus


class ProcessingResult:
    """Encapsulates the execution summary of a batch run."""
    def __init__(
        self,
        run_id: str,
        status: str,
        input_count: int,
        accepted_count: int,
        rejected_count: int,
        duplicate_count: int,
        processed_count: int,
        affected_dates: List[str],
        duration_sec: float,
        reconciliation_passed: bool,
        alerts_generated: int = 0
    ):
        self.run_id = run_id
        self.status = status
        self.input_count = input_count
        self.accepted_count = accepted_count
        self.rejected_count = rejected_count
        self.duplicate_count = duplicate_count
        self.processed_count = processed_count
        self.affected_dates = affected_dates
        self.duration_sec = duration_sec
        self.reconciliation_passed = reconciliation_passed
        self.alerts_generated = alerts_generated

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "input_count": self.input_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "duplicate_count": self.duplicate_count,
            "processed_count": self.processed_count,
            "affected_dates": self.affected_dates,
            "duration_sec": self.duration_sec,
            "reconciliation_passed": self.reconciliation_passed,
            "alerts_generated": self.alerts_generated,
        }


class TransactionProcessor:
    """End-to-end batch transaction processing engine."""

    def __init__(self, db: Session):
        self.db = db

    def process_file(
        self,
        file_path: Path,
        allow_rerun: bool = False
    ) -> ProcessingResult:
        """
        Process a CSV transaction file end-to-end.
        Guarantees idempotency and safe recovery.
        """
        file_path = Path(file_path)
        rows, meta = load_csv(file_path)
        file_hash = meta["file_hash"]
        source_file = file_path.name
        input_count = len(rows)

        # 1. Manage run lifecycle & idempotency check
        run, is_new = BatchManager.get_or_create_run(
            db=self.db,
            source_file=source_file,
            file_hash=file_hash,
            input_count=input_count,
            allow_rerun=allow_rerun
        )
        run_id = run.run_id

        try:
            return self._execute_pipeline(
                run_id=run_id,
                source_file=source_file,
                rows=rows
            )
        except Exception as e:
            self.db.rollback()
            BatchManager.fail_run(self.db, run_id, str(e), stage="EXECUTION", error=e)
            raise

    def process_records(
        self,
        records: List[Dict[str, Any]],
        source_name: str = "API_UPLOAD",
        allow_rerun: bool = True
    ) -> ProcessingResult:
        """Process an in-memory list of record dicts (e.g. from REST API upload)."""
        import hashlib
        content_repr = json.dumps(records, sort_keys=True).encode("utf-8")
        file_hash = hashlib.sha256(content_repr).hexdigest()
        input_count = len(records)

        # Wrap in expected loader row format
        rows = [
            {"line_number": idx + 1, "raw_row": json.dumps(r), "data": r}
            for idx, r in enumerate(records)
        ]

        run, is_new = BatchManager.get_or_create_run(
            db=self.db,
            source_file=source_name,
            file_hash=file_hash,
            input_count=input_count,
            allow_rerun=allow_rerun
        )
        run_id = run.run_id

        try:
            return self._execute_pipeline(
                run_id=run_id,
                source_file=source_name,
                rows=rows
            )
        except Exception as e:
            self.db.rollback()
            BatchManager.fail_run(self.db, run_id, str(e), stage="EXECUTION", error=e)
            raise

    def _execute_pipeline(
        self,
        run_id: str,
        source_file: str,
        rows: List[Dict[str, Any]]
    ) -> ProcessingResult:
        """Internal execution pipeline for validated and parsed records."""
        input_count = len(rows)

        # Pre-load known event IDs for fast duplicate lookup
        preloaded_event_ids: Set[str] = set()
        if input_count > 0:
            db_evts = self.db.query(RawEvent.event_id).all()
            preloaded_event_ids = {r[0] for r in db_evts}

        accepted_items: List[Dict[str, Any]] = []
        rejected_items: List[Dict[str, Any]] = []
        duplicate_items: List[Dict[str, Any]] = []
        seen_event_ids_in_batch: Set[str] = set()

        # Step 1: Validation and Classification
        for row_entry in rows:
            line_no = row_entry["line_number"]
            raw_data = row_entry["data"]

            # Schema validation
            is_valid, reason, code, validated_data = SchemaValidator.validate_record(raw_data)
            if not is_valid:
                rejected_items.append({
                    "line_number": line_no,
                    "raw_data": raw_data,
                    "reason": reason,
                    "code": code,
                })
                continue

            # Business reference validation
            ref_valid, ref_reason, ref_code = BusinessValidator.validate_reference_keys(validated_data)
            if not ref_valid:
                rejected_items.append({
                    "line_number": line_no,
                    "raw_data": raw_data,
                    "reason": ref_reason,
                    "code": ref_code,
                })
                continue

            # Duplicate check
            evt_id = validated_data["event_id"]
            is_dup = BusinessValidator.check_duplicate_event(
                event_id=evt_id,
                seen_in_batch=seen_event_ids_in_batch,
                db=self.db,
                preloaded_db_events=preloaded_event_ids
            )

            if is_dup:
                duplicate_items.append({
                    "line_number": line_no,
                    "data": validated_data,
                    "raw_row": row_entry["raw_row"]
                })
            else:
                seen_event_ids_in_batch.add(evt_id)
                preloaded_event_ids.add(evt_id)
                accepted_items.append({
                    "line_number": line_no,
                    "data": validated_data,
                    "raw_row": row_entry["raw_row"]
                })

        # Step 2: Quarantine rejected records
        rejected_count = QuarantineManager.quarantine_records(
            db=self.db,
            run_id=run_id,
            source_file=source_file,
            rejected_items=rejected_items
        )

        # Step 3: Record duplicate events in raw_events table for auditing
        now = datetime.now(timezone.utc)
        dup_raw_events = []
        for idx, dup in enumerate(duplicate_items):
            d = dup["data"]
            dup_raw_events.append(RawEvent(
                event_id=f"dup_{idx}_{uuid.uuid4().hex[:6]}_{d['event_id']}",
                run_id=run_id,
                transaction_id=d["transaction_id"],
                customer_id=d["customer_id"],
                product_id=d["product_id"],
                event_type=d["event_type"],
                amount=d["amount"],
                currency=d["currency"],
                event_timestamp=d["event_timestamp"],
                ingestion_timestamp=now,
                source_system=d.get("source_system", "UNKNOWN"),
                source_file=source_file,
                raw_payload=dup["raw_row"],
                status=RecordStatus.DUPLICATE.value,
                created_at=now,
            ))
        if dup_raw_events:
            self.db.bulk_save_objects(dup_raw_events)
            self.db.flush()

        # Step 4: Deterministic ordering of accepted events
        # Order by (event_timestamp, event_type_priority) where NEW=0, UPDATE=1, REVERSAL=2
        priority_map = {
            EventType.NEW.value: 0,
            EventType.UPDATE.value: 1,
            EventType.REVERSAL.value: 2
        }
        accepted_items.sort(
            key=lambda x: (
                x["data"]["event_timestamp"],
                priority_map.get(x["data"]["event_type"], 99)
            )
        )

        # Step 5: Process transaction state transitions
        affected_dates: Set[Any] = set()
        accepted_raw_events = []
        processed_count = 0

        # In-memory transaction cache to prevent duplicate inserts within the same batch
        tx_cache: Dict[str, Transaction] = {}
        batch_tx_ids = list({item["data"]["transaction_id"] for item in accepted_items})
        if batch_tx_ids:
            # Query in chunks of 500 to stay well under SQLite parameter limits
            chunk_size = 500
            for i in range(0, len(batch_tx_ids), chunk_size):
                chunk = batch_tx_ids[i:i + chunk_size]
                for t in self.db.query(Transaction).filter(Transaction.transaction_id.in_(chunk)).all():
                    tx_cache[t.transaction_id] = t

        for item in accepted_items:
            d = item["data"]
            evt_type = d["event_type"]
            tx_id = d["transaction_id"]
            evt_ts = d["event_timestamp"]
            amt = d["amount"]
            affected_dates.add(evt_ts.date())

            # Log to raw_events
            accepted_raw_events.append(RawEvent(
                event_id=d["event_id"],
                run_id=run_id,
                transaction_id=tx_id,
                customer_id=d["customer_id"],
                product_id=d["product_id"],
                event_type=evt_type,
                amount=amt,
                currency=d["currency"],
                event_timestamp=evt_ts,
                ingestion_timestamp=now,
                source_system=d.get("source_system", "UNKNOWN"),
                source_file=source_file,
                raw_payload=item["raw_row"],
                status=RecordStatus.ACCEPTED.value,
                created_at=now,
            ))

            # Apply state update
            if evt_type == EventType.NEW.value:
                existing_tx = tx_cache.get(tx_id)
                if not existing_tx:
                    new_tx = Transaction(
                        transaction_id=tx_id,
                        customer_id=d["customer_id"],
                        product_id=d["product_id"],
                        current_amount=amt,
                        currency=d["currency"],
                        status="ACTIVE",
                        is_reversed=False,
                        version=1,
                        first_event_timestamp=evt_ts,
                        latest_event_timestamp=evt_ts,
                        latest_event_id=d["event_id"],
                        last_run_id=run_id,
                    )
                    self.db.add(new_tx)
                    tx_cache[tx_id] = new_tx

                    hist = TransactionHistory(
                        transaction_id=tx_id,
                        event_id=d["event_id"],
                        event_type="NEW",
                        previous_amount=Decimal("0.00"),
                        new_amount=amt,
                        event_timestamp=evt_ts,
                        applied_at=now,
                        run_id=run_id,
                    )
                    self.db.add(hist)
                    processed_count += 1
                else:
                    # Existing transaction - duplicate or out-of-order NEW
                    hist = TransactionHistory(
                        transaction_id=tx_id,
                        event_id=d["event_id"],
                        event_type="NEW_DUPLICATE_IGNORED",
                        previous_amount=existing_tx.current_amount,
                        new_amount=existing_tx.current_amount,
                        event_timestamp=evt_ts,
                        applied_at=now,
                        run_id=run_id,
                    )
                    self.db.add(hist)

            elif evt_type == EventType.UPDATE.value:
                success, msg, tx = UpdateHandler.process_update(self.db, d, run_id, tx_cache=tx_cache)
                if success:
                    processed_count += 1
                if tx and tx.first_event_timestamp:
                    affected_dates.add(tx.first_event_timestamp.date())

            elif evt_type == EventType.REVERSAL.value:
                success, msg, tx = ReversalHandler.process_reversal(self.db, d, run_id, tx_cache=tx_cache)
                if success:
                    processed_count += 1
                if tx and tx.first_event_timestamp:
                    affected_dates.add(tx.first_event_timestamp.date())

        if accepted_raw_events:
            self.db.bulk_save_objects(accepted_raw_events)
            self.db.flush()

        # Step 6: Historical Metric Recomputation for all affected business dates
        if affected_dates:
            RecomputationEngine.recompute_dates(self.db, affected_dates, run_id=run_id)

        # Step 7: Profiling and Alert Generation
        alerts_count = 0
        try:
            from app.profiling.profiler import Profiler
            from app.alerts.alert_engine import AlertEngine
            profile = Profiler.create_batch_profile(self.db, run_id, rows, accepted_items, rejected_items)
            alerts = AlertEngine.evaluate_run(self.db, run_id, profile)
            alerts_count = len(alerts)
        except Exception as prof_err:
            print(f"Profiling notice: {prof_err}")

        # Step 8: Terminal Reconciliation Check
        # Check: Input rows = accepted rows + rejected rows + duplicate rows
        accepted_count = len(accepted_items)
        duplicate_count = len(duplicate_items)
        reconciled = (input_count == (accepted_count + rejected_count + duplicate_count))

        # Step 9: Finalize Run State
        completed_run = BatchManager.complete_run(
            db=self.db,
            run_id=run_id,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            processed_count=processed_count,
        )

        self.db.commit()

        # Step 10: Generate audit reports
        try:
            from app.reporting.report_generator import ReportGenerator
            report_gen = ReportGenerator()
            report_gen.generate_all_reports(self.db, run_id=run_id)
        except Exception as rep_err:
            print(f"Report generation notice: {rep_err}")

        return ProcessingResult(
            run_id=run_id,
            status=completed_run.status,
            input_count=input_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            processed_count=processed_count,
            affected_dates=[d.isoformat() for d in sorted(affected_dates)],
            duration_sec=completed_run.execution_duration_sec or 0.0,
            reconciliation_passed=reconciled,
            alerts_generated=alerts_count,
        )
