"""Repository for batch processing runs and raw events."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.database.models import ProcessingRun, RawEvent, RejectedRecord


class BatchRepository:
    """Encapsulates database operations for batches, events, and rejections."""

    @staticmethod
    def get_run(db: Session, run_id: str) -> Optional[ProcessingRun]:
        return db.query(ProcessingRun).filter_by(run_id=run_id).first()

    @staticmethod
    def get_run_by_hash(db: Session, file_hash: str) -> Optional[ProcessingRun]:
        return db.query(ProcessingRun).filter_by(file_hash=file_hash).first()

    @staticmethod
    def list_runs(
        db: Session,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ProcessingRun]:
        query = db.query(ProcessingRun)
        if status:
            query = query.filter_by(status=status.upper())
        return query.order_by(ProcessingRun.start_time.desc()).offset(offset).limit(limit).all()

    @staticmethod
    def get_rejected_records(
        db: Session,
        run_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[RejectedRecord]:
        query = db.query(RejectedRecord)
        if run_id:
            query = query.filter_by(run_id=run_id)
        return query.order_by(RejectedRecord.rejected_at.desc()).offset(offset).limit(limit).all()
