"""API routes for daily business metrics and quality profiles."""
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.database_models import DailyMetric, DataQualityProfile
from app.api.schemas import DailyMetricResponse, DataQualityProfileResponse

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/daily", response_model=List[DailyMetricResponse])
def get_daily_metrics(
    start_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    dimension: str = Query("TOTAL", description="Dimension type (TOTAL, PRODUCT, CUSTOMER)"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Retrieve daily aggregate business metrics."""
    query = db.query(DailyMetric).filter(DailyMetric.dimension_type == dimension.upper())
    if start_date:
        query = query.filter(DailyMetric.metric_date >= start_date)
    if end_date:
        query = query.filter(DailyMetric.metric_date <= end_date)
    return query.order_by(DailyMetric.metric_date.desc()).limit(limit).all()


@router.get("/profiles", response_model=List[DataQualityProfileResponse])
def get_quality_profiles(
    run_id: Optional[str] = Query(None, description="Filter by run ID"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Retrieve batch data quality profiles."""
    query = db.query(DataQualityProfile)
    if run_id:
        query = query.filter(DataQualityProfile.run_id == run_id)
    return query.order_by(DataQualityProfile.created_at.desc()).limit(limit).all()

