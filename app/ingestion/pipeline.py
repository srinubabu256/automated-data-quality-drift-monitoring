"""End-to-end Ingestion Pipeline orchestrating ingestion, validation, processing, profiling, and alerts."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from app.ingestion.loader import load_csv, compute_file_hash, FileFormatError
from app.ingestion.batch_manager import BatchManager, DuplicateFileError
from app.validation.schema_validator import SchemaValidator
from app.validation.business_validator import BusinessValidator
from app.validation.quarantine import QuarantineManager
from app.processing.transaction_processor import TransactionProcessor
from app.profiling.profiler import BatchProfiler
from app.alerts.alert_engine import AlertEngine
from app.reporting.reconciliation import ReconciliationEngine
from app.reporting.report_generator import ReportGenerator
from app.models.database_models import ProcessingRun, RawEvent

logger = logging.getLogger("ingestion_pipeline")


class PipelineResult:
    """Encapsulates execution results of a batch ingestion run."""
    def __init__(
        self,
        run_id: str,
        status: str,
        input_count: int,
        accepted_count: int,
        rejected_count: int,
        duplicate_count: int,
        processed_count: int,
        reconciliation: Dict[str, Any],
        alerts_generated: int,
        execution_duration_sec: float,
        error_message: Optional[str] = None
    ):
        self.run_id = run_id
        self.status = status
        self.input_count = input_count
        self.accepted_count = accepted_count
        self.rejected_count = rejected_count
        self.duplicate_count = duplicate_count
        self.processed_count = processed_count
        self.reconciliation = reconciliation
        self.alerts_generated = alerts_generated
        self.execution_duration_sec = execution_duration_sec
        self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "input_count": self.input_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "duplicate_count": self.duplicate_count,
            "processed_count": self.processed_count,
            "reconciliation": self.reconciliation,
            "alerts_generated": self.alerts_generated,
            "execution_duration_sec": self.execution_duration_sec,
            "error_message": self.error_message,
        }


class IngestionPipeline:
    """Executes the full data engineering ingestion lifecycle idempotently."""

    @classmethod
    def run_file_pipeline(
        cls,
        db: Session,
        file_path: Path,
        allow_rerun: bool = False
    ) -> PipelineResult:
        """
        Executes end-to-end ingestion on a CSV file.
        Idempotent: raises or returns safe result on duplicate file hashes.
        """
        source_file = str(file_path.name)
        file_hash = compute_file_hash(file_path)

        # 1. Load CSV data
        try:
            raw_rows, meta = load_csv(file_path)
        except Exception as e:
            logger.error(f"Failed to load CSV {file_path}: {e}")
            run_id = f"err_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            BatchManager.fail_run(db, run_id, f"CSV load failed: {e}", stage="LOAD_CSV", error=e)
            raise

        input_count = len(raw_rows)

        # 2. Check or create run (Idempotency enforcement)
        try:
            run, is_new = BatchManager.get_or_create_run(
                db=db,
                source_file=source_file,
                file_hash=file_hash,
                input_count=input_count,
                allow_rerun=allow_rerun
            )
        except DuplicateFileError as e:
            logger.warning(f"Idempotent check: file {source_file} (hash {file_hash}) already processed in run {e.run_id}")
            recon = ReconciliationEngine.reconcile_run(db, e.run_id)
            existing_run = db.query(ProcessingRun).filter_by(run_id=e.run_id).first()
            return PipelineResult(
                run_id=e.run_id,
                status="DUPLICATE_IGNORED",
                input_count=existing_run.input_count if existing_run else 0,
                accepted_count=existing_run.accepted_count if existing_run else 0,
                rejected_count=existing_run.rejected_count if existing_run else 0,
                duplicate_count=existing_run.duplicate_count if existing_run else 0,
                processed_count=existing_run.processed_count if existing_run else 0,
                reconciliation=recon,
                alerts_generated=0,
                execution_duration_sec=0.0,
                error_message=f"Duplicate file: already processed in {e.run_id}",
            )

        run_id = run.run_id

        # 3. Handle empty batch
        if input_count == 0:
            logger.info(f"Empty batch received for file {source_file}. Completing run {run_id}.")
            BatchManager.complete_run(db, run_id, 0, 0, 0, 0)
            recon = ReconciliationEngine.reconcile_run(db, run_id)
            profile = BatchProfiler.profile_run(db, run_id, amounts=[])
            alerts = AlertEngine.evaluate_batch(db, profile)
            return PipelineResult(
                run_id=run_id,
                status="COMPLETED",
                input_count=0,
                accepted_count=0,
                rejected_count=0,
                duplicate_count=0,
                processed_count=0,
                reconciliation=recon,
                alerts_generated=len(alerts),
                execution_duration_sec=0.0,
            )

        # 4. Validation and deduplication
        seen_event_ids: Set[str] = set()
        # Preload existing DB event IDs for performance
        existing_db_events = {
            r[0] for r in db.query(RawEvent.event_id).all()
        }

        accepted_records: List[Dict[str, Any]] = []
        rejected_items: List[Dict[str, Any]] = []
        duplicate_count = 0
        accepted_amounts: List[float] = []

        for row in raw_rows:
            line_no = row["line_number"]
            row_data = row["data"]
            raw_event_id = str(row_data.get("event_id", "")).strip()

            # Case A: Duplicate event_id check
            if raw_event_id and BusinessValidator.check_duplicate_event(
                raw_event_id, seen_event_ids, db, preloaded_db_events=existing_db_events
            ):
                duplicate_count += 1
                # Log as duplicate event for audit traceability
                continue

            # Case B: Schema Validation
            is_valid, reason, code, validated_data = SchemaValidator.validate_record(row_data)
            if not is_valid:
                rejected_items.append({
                    "line_number": line_no,
                    "raw_data": row_data,
                    "reason": reason,
                    "code": code,
                })
                continue

            # Case C: Business Validation
            is_biz_valid, biz_reason, biz_code = BusinessValidator.validate_reference_keys(validated_data)
            if not is_biz_valid:
                rejected_items.append({
                    "line_number": line_no,
                    "raw_data": row_data,
                    "reason": biz_reason,
                    "code": biz_code,
                })
                continue

            # Record is valid & accepted
            seen_event_ids.add(validated_data["event_id"])
            existing_db_events.add(validated_data["event_id"])
            validated_data["line_number"] = line_no
            validated_data["raw_data"] = row_data
            accepted_records.append(validated_data)
            if validated_data.get("amount") is not None:
                accepted_amounts.append(float(validated_data["amount"]))

        # 5. Quarantine rejected records
        rejected_count = QuarantineManager.quarantine_records(db, run_id, source_file, rejected_items)
        accepted_count = len(accepted_records)

        # 6. Verify row conservation before mutating state:
        # Input = Accepted + Rejected + Duplicate
        if input_count != (accepted_count + rejected_count + duplicate_count):
            err_msg = (
                f"Row conservation violation! Input={input_count}, "
                f"Sum={accepted_count + rejected_count + duplicate_count}"
            )
            logger.error(err_msg)
            BatchManager.fail_run(db, run_id, err_msg, stage="VALIDATION")
            raise ValueError(err_msg)

        # 7. Process Transactions (NEW, UPDATE, REVERSAL) and Recompute historical metrics
        try:
            processed_count, affected_dates = TransactionProcessor.process_batch(
                db=db,
                run_id=run_id,
                source_file=source_file,
                accepted_records=accepted_records
            )
        except Exception as e:
            logger.error(f"Transaction processing failed: {e}", exc_info=True)
            db.rollback()
            BatchManager.fail_run(db, run_id, f"Processing failed: {e}", stage="TRANSACTION_PROCESSING", error=e)
            raise

        # 8. Complete run status
        completed_run = BatchManager.complete_run(
            db=db,
            run_id=run_id,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            processed_count=processed_count
        )

        # 9. Profile batch and generate alerts
        profile = BatchProfiler.profile_run(db, run_id, amounts=accepted_amounts)
        alerts = AlertEngine.evaluate_batch(db, profile)

        # 10. Reconcile run and generate reports
        reconciliation_data = ReconciliationEngine.reconcile_run(db, run_id)
        report_gen = ReportGenerator()
        report_gen.generate_all_reports(db, run_id=run_id)

        logger.info(
            f"Successfully finished ingestion run {run_id}: "
            f"Input={input_count}, Accepted={accepted_count}, Rejected={rejected_count}, "
            f"Duplicates={duplicate_count}, Processed={processed_count}, Alerts={len(alerts)}"
        )

        return PipelineResult(
            run_id=run_id,
            status=completed_run.status,
            input_count=input_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            processed_count=processed_count,
            reconciliation=reconciliation_data,
            alerts_generated=len(alerts),
            execution_duration_sec=completed_run.execution_duration_sec,
        )
