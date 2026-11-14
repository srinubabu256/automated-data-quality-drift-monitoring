"""Drift service layer coordinating drift analysis and query retrieval."""
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.database.models import DriftAnalysisResult
from app.database.repositories.alert_repository import AlertRepository
from app.drift.detector import DriftDetector


class DriftService:
    """Provides business logic operations for statistical drift analysis."""

    @staticmethod
    def execute_drift_analysis(
        records: Any,
        db: Session,
        run_id: str,
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
    ) -> Dict[str, Any]:
        return DriftDetector.analyze(
            records=records,
            run_id=run_id,
            baseline_version=baseline_version,
            dataset_name=dataset_name,
            db=db,
            save_results=True,
        )

    @staticmethod
    def query_drift_results(
        db: Session,
        run_id: Optional[str] = None,
        drift_type: Optional[str] = None,
        drift_detected: Optional[bool] = None,
        limit: int = 100,
    ) -> List[DriftAnalysisResult]:
        return AlertRepository.get_drift_results(
            db=db,
            run_id=run_id,
            drift_type=drift_type,
            drift_detected=drift_detected,
            limit=limit,
        )
