"""Repository for daily business metrics and quality profiles."""
from datetime import date
from typing import List, Optional
from sqlalchemy.orm import Session

from app.database.models import DailyMetric, DataQualityProfile


class MetricRepository:
    """Encapsulates database operations for aggregate metrics and quality profiles."""

    @staticmethod
    def get_daily_metrics(
        db: Session,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        dimension: str = "TOTAL",
        limit: int = 100,
    ) -> List[DailyMetric]:
        dim_str = dimension if isinstance(dimension, str) else "TOTAL"
        query = db.query(DailyMetric).filter(DailyMetric.dimension_type == dim_str.upper())
        if start_date:
            query = query.filter(DailyMetric.metric_date >= start_date)
        if end_date:
            query = query.filter(DailyMetric.metric_date <= end_date)
        return query.order_by(DailyMetric.metric_date.desc()).limit(limit).all()

    @staticmethod
    def get_quality_profiles(
        db: Session,
        run_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[DataQualityProfile]:
        query = db.query(DataQualityProfile)
        if run_id:
            query = query.filter_by(run_id=run_id)
        return query.order_by(DataQualityProfile.created_at.desc()).limit(limit).all()
