"""API routes for batch uploads and execution run tracking."""
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.database_models import ProcessingRun
from app.processing.transaction_processor import TransactionProcessor
from app.ingestion.batch_manager import DuplicateFileError
from app.api.schemas import ProcessingRunResponse, BatchUploadResponse

router = APIRouter(prefix="/batches", tags=["Batches"])


@router.post("/upload", response_model=BatchUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_batch_file(
    file: UploadFile = File(...),
    allow_rerun: bool = Query(False, description="Allow re-running file with identical hash"),
    db: Session = Depends(get_db)
):
    """
    Upload a transaction CSV batch file for processing.
    Validates, isolates errors to quarantine, tracks transactions,
    recomputes daily metrics, and generates explainable alerts.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files (.csv) are accepted for batch upload."
        )

    # Save uploaded file temporarily to input directory
    input_dir = Path(settings.DATA_INPUT_DIR)
    input_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = input_dir / f"upload_{file.filename}"

    try:
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {e}"
        )

    try:
        processor = TransactionProcessor(db=db)
        result = processor.process_file(file_path=temp_file_path, allow_rerun=allow_rerun)
        return BatchUploadResponse(**result.to_dict())
    except DuplicateFileError as dup_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(dup_err)
        )
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Batch processing pipeline failed: {err}"
        )


@router.get("", response_model=List[ProcessingRunResponse])
def list_batches(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List all processing runs with optional status filtering and pagination."""
    query = db.query(ProcessingRun)
    if status_filter:
        query = query.filter(ProcessingRun.status == status_filter.upper())
    return query.order_by(ProcessingRun.start_time.desc()).offset(offset).limit(limit).all()


@router.get("/{run_id}", response_model=ProcessingRunResponse)
def get_batch_by_id(run_id: str, db: Session = Depends(get_db)):
    """Retrieve execution metrics and status for a specific run ID."""
    run = db.query(ProcessingRun).filter_by(run_id=run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Processing run '{run_id}' not found."
        )
    return run
