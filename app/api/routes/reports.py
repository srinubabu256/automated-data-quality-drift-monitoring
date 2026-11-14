"""API routes for reconciliation auditing and rejected records inspection."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.database_models import ProcessingRun, RejectedRecord
from app.reporting.reconciliation import ReconciliationChecker
from app.validation.quarantine import QuarantineManager
from app.api.schemas import ReconciliationResponse, RejectedRecordResponse

router = APIRouter(tags=["Reports & Quarantine"])


@router.get("/reports/reconciliation", response_model=ReconciliationResponse)
def get_reconciliation_report(
    run_id: Optional[str] = Query(None, description="Run ID (defaults to latest completed run)"),
    db: Session = Depends(get_db)
):
    """Generate and return terminal reconciliation report for a processing run."""
    if not run_id:
        latest = db.query(ProcessingRun).filter_by(status="COMPLETED").order_by(ProcessingRun.start_time.desc()).first()
        if not latest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No completed processing runs found to reconcile."
            )
        run_id = latest.run_id

    result = ReconciliationChecker.verify_run_reconciliation(db, run_id)
    if not result.get("reconciled") and "error" in result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["error"]
        )
    return result


@router.get("/rejected-records", response_model=List[RejectedRecordResponse])
def get_rejected_records(
    run_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Retrieve quarantined invalid records with rejection reasons and line numbers."""
    limit_val = limit if isinstance(limit, int) else 50
    offset_val = offset if isinstance(offset, int) else 0
    return QuarantineManager.get_rejected_records(
        db=db,
        run_id=run_id,
        limit=limit_val,
        offset=offset_val
    )

