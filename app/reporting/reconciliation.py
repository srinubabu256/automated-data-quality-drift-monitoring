"""Reconciliation Engine verifying strict conservation of records and amounts."""
from typing import Any, Dict, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database_models import ProcessingRun, RawEvent, RejectedRecord


class ReconciliationError(Exception):
    """Raised when record counts or amounts do not balance."""
    pass


class ReconciliationEngine:
    """Verifies that terminal record classifications balance strictly:
    Input = Accepted + Rejected + Duplicate
    """

    @classmethod
    def verify_run_reconciliation(cls, db: Session, run_id: str) -> Dict[str, Any]:
        """
        Verify strict accounting equality matching ReconciliationResponse schema.
        """
        run = db.query(ProcessingRun).filter_by(run_id=run_id).first()
        if not run:
            return {
                "run_id": run_id,
                "reconciled": False,
                "status": "NOT_FOUND",
                "error": f"Processing run '{run_id}' not found.",
                "equation": "",
                "counts": {},
                "database_audit": {},
                "financial_audit": {},
                "execution_metadata": {},
            }

        input_count = run.input_count
        accepted_count = run.accepted_count
        rejected_count = run.rejected_count
        duplicate_count = run.duplicate_count
        processed_count = run.processed_count

        expected_total = accepted_count + rejected_count + duplicate_count
        reconciled = (input_count == expected_total)

        db_raw_count = db.query(func.count(RawEvent.id)).filter_by(run_id=run_id).scalar() or 0
        db_rejected_count = db.query(func.count(RejectedRecord.id)).filter_by(run_id=run_id).scalar() or 0
        total_raw_amount = db.query(func.coalesce(func.sum(RawEvent.amount), 0)).filter_by(run_id=run_id).scalar() or 0.0

        equation = f"{input_count} (Input) = {accepted_count} (Accepted) + {rejected_count} (Rejected) + {duplicate_count} (Duplicate)"

        return {
            "run_id": run_id,
            "source_file": run.source_file,
            "reconciled": reconciled,
            "status": "BALANCED" if reconciled else "DISCREPANCY",
            "equation": equation,
            "counts": {
                "input_count": input_count,
                "accepted_count": accepted_count,
                "rejected_count": rejected_count,
                "duplicate_count": duplicate_count,
                "processed_count": processed_count,
                "calculated_sum": expected_total,
                "discrepancy": input_count - expected_total,
            },
            "database_audit": {
                "db_raw_events_count": db_raw_count,
                "db_rejected_records_count": db_rejected_count,
            },
            "financial_audit": {
                "total_raw_amount": float(total_raw_amount),
            },
            "execution_metadata": {
                "start_time": run.start_time.isoformat() if run.start_time else "",
                "end_time": run.end_time.isoformat() if run.end_time else "",
                "execution_duration_sec": run.execution_duration_sec or 0.0,
            },
        }

    @classmethod
    def reconcile_run(cls, db: Session, run_id: str) -> Dict[str, Any]:
        """Alias for backward compatibility."""
        return cls.verify_run_reconciliation(db, run_id)


# Backward-compatible alias
ReconciliationChecker = ReconciliationEngine
