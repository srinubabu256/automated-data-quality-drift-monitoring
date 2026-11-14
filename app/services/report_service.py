"""Report service layer coordinating reconciliation and analytics exports."""
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.database.models import DailyMetric, DataQualityAlert, DataQualityProfile
from app.database.repositories.alert_repository import AlertRepository
from app.database.repositories.metric_repository import MetricRepository
from app.reporting.reconciliation import ReconciliationEngine
from app.reporting.report_generator import ReportGenerator


class ReportService:
    """Provides business logic operations for reconciliation and compliance reports."""

    @staticmethod
    def get_reconciliation_report(db: Session, run_id: str) -> Dict[str, Any]:
        return ReconciliationEngine.verify_run_reconciliation(db=db, run_id=run_id)

    @staticmethod
    def get_alerts(
        db: Session,
        run_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[DataQualityAlert]:
        return AlertRepository.get_alerts(db=db, run_id=run_id, severity=severity, limit=limit)

    @staticmethod
    def export_all_reports(db: Session, output_dir: Optional[str] = None) -> Dict[str, str]:
        generator = ReportGenerator(db=db, output_dir=output_dir)
        return generator.generate_all_reports()
