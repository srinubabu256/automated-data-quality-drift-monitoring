"""Batch Manager for ingestion lifecycle, idempotency checking, and run status tracking."""
import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models.database_models import ProcessingRun, ProcessingError
from app.models.enums import BatchStatus


class DuplicateFileError(Exception):
    """Raised when an identical file has already been successfully processed."""
    def __init__(self, run_id: str, file_hash: str):
        super().__init__(f"File with hash {file_hash} was already successfully processed in run {run_id}.")
        self.run_id = run_id
        self.file_hash = file_hash


class BatchManager:
    """Manages processing run states, idempotency checks, and execution metrics."""

    @staticmethod
    def get_or_create_run(
        db: Session,
        source_file: str,
        file_hash: str,
        input_count: int,
        allow_rerun: bool = False
    ) -> Tuple[ProcessingRun, bool]:
        """
        Check for existing run with identical hash.
        Returns (run, is_new).
        If already COMPLETED and allow_rerun is False, raises DuplicateFileError.
        If already FAILED, restarts run as RETRIED or creates new retry run.
        """
        existing_run = db.query(ProcessingRun).filter_by(file_hash=file_hash).first()

        if existing_run:
            if existing_run.status == BatchStatus.COMPLETED and not allow_rerun:
                raise DuplicateFileError(existing_run.run_id, file_hash)

            if existing_run.status == BatchStatus.FAILED:
                # Reuse/retry the failed run or create a new run linked to it
                existing_run.status = BatchStatus.PROCESSING
                existing_run.start_time = datetime.now(timezone.utc)
                existing_run.failure_reason = None
                existing_run.input_count = input_count
                db.commit()
                db.refresh(existing_run)
                return existing_run, False

        # Generate unique run_id
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{timestamp_str}_{uuid.uuid4().hex[:8]}"

        new_run = ProcessingRun(
            run_id=run_id,
            source_file=source_file,
            file_hash=file_hash,
            status=BatchStatus.PROCESSING,
            input_count=input_count,
            start_time=datetime.now(timezone.utc),
        )
        db.add(new_run)
        db.commit()
        db.refresh(new_run)
        return new_run, True

    @staticmethod
    def complete_run(
        db: Session,
        run_id: str,
        accepted_count: int,
        rejected_count: int,
        duplicate_count: int,
        processed_count: int
    ) -> ProcessingRun:
        """Mark run as COMPLETED and record final counts and execution duration."""
        run = db.query(ProcessingRun).filter_by(run_id=run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found")

        end_time = datetime.now(timezone.utc)
        # Handle start_time whether it has tzinfo or not
        st = run.start_time
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        duration = (end_time - st).total_seconds()

        run.status = BatchStatus.COMPLETED
        run.accepted_count = accepted_count
        run.rejected_count = rejected_count
        run.duplicate_count = duplicate_count
        run.processed_count = processed_count
        run.end_time = end_time
        run.execution_duration_sec = duration

        db.commit()
        db.refresh(run)
        return run

    @staticmethod
    def fail_run(
        db: Session,
        run_id: str,
        reason: str,
        stage: str = "PROCESSING",
        error: Optional[Exception] = None
    ) -> ProcessingRun:
        """Mark run as FAILED and log error details."""
        run = db.query(ProcessingRun).filter_by(run_id=run_id).first()
        if run:
            end_time = datetime.now(timezone.utc)
            st = run.start_time
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            duration = (end_time - st).total_seconds()

            run.status = BatchStatus.FAILED
            run.failure_reason = reason
            run.end_time = end_time
            run.execution_duration_sec = duration

        # Record in processing_errors
        err_type = type(error).__name__ if error else "PipelineFailure"
        stack = traceback.format_exc() if error else None
        err_entry = ProcessingError(
            run_id=run_id,
            stage=stage,
            error_type=err_type,
            error_message=reason,
            stack_trace=stack,
        )
        db.add(err_entry)
        db.commit()

        if run:
            db.refresh(run)
        return run

