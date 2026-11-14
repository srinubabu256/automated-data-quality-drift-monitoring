"""Baseline service layer managing baseline versions and comparison."""
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.database.models import BaselineProfile
from app.database.repositories.baseline_repository import BaselineRepository
from app.profiling.baseline import BaselineManager


class BaselineService:
    """Provides business logic operations for reference baseline profiles."""

    @staticmethod
    def get_active(db: Session, version: Optional[str] = None) -> Optional[BaselineProfile]:
        return BaselineRepository.get_active(db=db, version=version)

    @staticmethod
    def list_baselines(db: Session) -> List[BaselineProfile]:
        return BaselineRepository.list_all(db=db)

    @staticmethod
    def create_or_update(
        db: Session,
        version: str,
        baseline_name: str,
        metrics: Dict[str, float],
        column_baselines: Optional[Any] = None,
        is_active: bool = True,
    ) -> BaselineProfile:
        return BaselineManager.create_or_update_baseline(
            db=db,
            version=version,
            baseline_name=baseline_name,
            metrics=metrics,
            column_baselines=column_baselines,
            is_active=is_active,
        )
