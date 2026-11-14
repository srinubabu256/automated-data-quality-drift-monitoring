"""Batch service layer handling batch execution and queries."""
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.database.models import ProcessingRun, RejectedRecord
from app.database.repositories.batch_repository import BatchRepository
from app.ingestion.pipeline import IngestionPipeline, PipelineExecutionResult


class BatchService:
    """Provides business logic operations for transaction batch files and runs."""

    @staticmethod
    def process_batch_file(
        file_path: Path,
        db: Session,
        allow_rerun: bool = False,
    ) -> PipelineExecutionResult:
        pipeline = IngestionPipeline(db=db)
        return pipeline.run(file_path=file_path, allow_rerun=allow_rerun)

    @staticmethod
    def get_run(db: Session, run_id: str) -> Optional[ProcessingRun]:
        return BatchRepository.get_run(db=db, run_id=run_id)

    @staticmethod
    def list_runs(
        db: Session,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ProcessingRun]:
        return BatchRepository.list_runs(db=db, status=status, limit=limit, offset=offset)

    @staticmethod
    def get_rejected_records(
        db: Session,
        run_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[RejectedRecord]:
        return BatchRepository.get_rejected_records(db=db, run_id=run_id, limit=limit, offset=offset)
