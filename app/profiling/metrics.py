"""Statistical metric calculations for profiling batches and querying daily metrics."""
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional
import numpy as np
from sqlalchemy.orm import Session
from app.models.database_models import DailyMetric


class ProfilingMetrics:
    """Computes distribution and summary statistics for batch profiling."""

    @staticmethod
    def calculate_numeric_stats(amounts: List[float]) -> Dict[str, float]:
        """Calculates mean, std, min, max, median, and p95 for a numeric sequence."""
        if not amounts:
            return {
                "mean": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0,
                "median": 0.0,
                "p95": 0.0,
            }

        arr = np.array(amounts, dtype=float)
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "median": float(np.median(arr)),
            "p95": float(np.percentile(arr, 95)),
        }

    @staticmethod
    def calculate_null_rate(total_count: int, invalid_or_null_count: int) -> float:
        """Computes proportion of null or rejected records."""
        if total_count == 0:
            return 0.0
        return round(float(invalid_or_null_count) / float(total_count), 4)


class DailyMetricsService:
    """Provides querying and filtering of precomputed daily metrics."""

    @staticmethod
    def get_metrics(
        db: Session,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        dimension_type: Optional[str] = "TOTAL",
        dimension_value: Optional[str] = "ALL",
        limit: int = 100,
        offset: int = 0
    ) -> List[DailyMetric]:
        """Fetch daily metrics filtered by date range and dimension."""
        query = db.query(DailyMetric)

        if start_date:
            query = query.filter(DailyMetric.metric_date >= start_date)
        if end_date:
            query = query.filter(DailyMetric.metric_date <= end_date)
        if dimension_type:
            query = query.filter(DailyMetric.dimension_type == dimension_type)
        if dimension_value:
            query = query.filter(DailyMetric.dimension_value == dimension_value)

        return query.order_by(DailyMetric.metric_date.desc()).offset(offset).limit(limit).all()

    @staticmethod
    def get_metric_by_date(
        db: Session,
        metric_date: date,
        dimension_type: str = "TOTAL",
        dimension_value: str = "ALL"
    ) -> Optional[DailyMetric]:
        """Fetch a specific daily metric row."""
        return db.query(DailyMetric).filter_by(
            metric_date=metric_date,
            dimension_type=dimension_type,
            dimension_value=dimension_value
        ).first()
