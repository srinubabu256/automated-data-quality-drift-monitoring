"""Repository for data quality anomaly alerts and drift analysis results."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.database.models import DataQualityAlert, DriftAnalysisResult


class AlertRepository:
    """Encapsulates database queries for alerts and drift analysis findings."""

    @staticmethod
    def get_alerts(
        db: Session,
        run_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[DataQualityAlert]:
        query = db.query(DataQualityAlert)
        if run_id:
            query = query.filter_by(run_id=run_id)
        if severity:
            query = query.filter_by(severity=severity.upper())
        return query.order_by(DataQualityAlert.created_at.desc()).limit(limit).all()

    @staticmethod
    def get_drift_results(
        db: Session,
        run_id: Optional[str] = None,
        drift_type: Optional[str] = None,
        drift_detected: Optional[bool] = None,
        limit: int = 100,
    ) -> List[DriftAnalysisResult]:
        query = db.query(DriftAnalysisResult)
        if run_id:
            query = query.filter_by(run_id=run_id)
        if drift_type:
            query = query.filter_by(drift_type=drift_type.upper())
        if drift_detected is not None:
            query = query.filter_by(drift_detected=drift_detected)
        return query.order_by(DriftAnalysisResult.id.desc()).limit(limit).all()
