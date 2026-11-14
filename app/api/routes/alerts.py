"""API routes for explainable data quality anomaly alerts."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.database_models import DataQualityAlert
from app.api.schemas import AlertResponse

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=List[AlertResponse])
def get_alerts(
    run_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Retrieve explainable data quality anomaly alerts."""
    query = db.query(DataQualityAlert)
    if run_id:
        query = query.filter(DataQualityAlert.run_id == run_id)
    if severity:
        query = query.filter(DataQualityAlert.severity == severity.upper())
    return query.order_by(DataQualityAlert.created_at.desc()).limit(limit).all()


# Backward-compatible alias
list_alerts = get_alerts

