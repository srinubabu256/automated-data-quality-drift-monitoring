"""Baseline Profile Manager for tracking, versioning, and comparing system baselines."""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.database_models import BaselineProfile
from app.config import settings

logger = logging.getLogger("baseline_manager")


class BaselineManager:
    """Manages baseline profile versions, retrieval, and updates."""

    @staticmethod
    def get_active_baseline(db: Session, version: Optional[str] = None) -> Optional[BaselineProfile]:
        """
        Retrieve the active baseline profile, or a specific version if specified.
        Falls back to configured settings.BASELINE_VERSION or latest active.
        """
        target_version = version or settings.BASELINE_VERSION
        profile = db.query(BaselineProfile).filter_by(version=target_version).first()
        if not profile:
            profile = db.query(BaselineProfile).filter_by(is_active=True).order_by(BaselineProfile.id.desc()).first()
        return profile

    @staticmethod
    def list_baselines(db: Session) -> List[BaselineProfile]:
        """List all available baseline profiles."""
        return db.query(BaselineProfile).order_by(BaselineProfile.id.desc()).all()

    @staticmethod
    def create_or_update_baseline(
        db: Session,
        version: str,
        baseline_name: str,
        metrics: Dict[str, float],
        is_active: bool = True
    ) -> BaselineProfile:
        """
        Create a new baseline profile version or update an existing one.
        If is_active is True, other baselines can be deactivated.
        """
        profile = db.query(BaselineProfile).filter_by(version=version).first()
        now = datetime.now(timezone.utc)

        if is_active:
            # Optionally mark other baselines as inactive
            db.query(BaselineProfile).filter(BaselineProfile.version != version).update({"is_active": False})

        if not profile:
            profile = BaselineProfile(
                version=version,
                baseline_name=baseline_name,
                record_volume=int(metrics.get("record_volume", 1000)),
                null_rate=float(metrics.get("null_rate", 0.02)),
                mean_amount=float(metrics.get("mean_amount", 150.0)),
                std_amount=float(metrics.get("std_amount", 50.0)),
                min_amount=float(metrics.get("min_amount", 5.0)),
                max_amount=float(metrics.get("max_amount", 500.0)),
                median_amount=float(metrics.get("median_amount", 140.0)),
                p95_amount=float(metrics.get("p95_amount", 300.0)),
                event_freshness_sec=float(metrics.get("event_freshness_sec", 3600.0)),
                is_active=is_active,
                created_at=now,
            )
            db.add(profile)
        else:
            profile.baseline_name = baseline_name
            profile.record_volume = int(metrics.get("record_volume", profile.record_volume))
            profile.null_rate = float(metrics.get("null_rate", profile.null_rate))
            profile.mean_amount = float(metrics.get("mean_amount", profile.mean_amount))
            profile.std_amount = float(metrics.get("std_amount", profile.std_amount))
            profile.min_amount = float(metrics.get("min_amount", profile.min_amount))
            profile.max_amount = float(metrics.get("max_amount", profile.max_amount))
            profile.median_amount = float(metrics.get("median_amount", profile.median_amount))
            profile.p95_amount = float(metrics.get("p95_amount", profile.p95_amount))
            profile.event_freshness_sec = float(metrics.get("event_freshness_sec", profile.event_freshness_sec))
            profile.is_active = is_active

        db.commit()
        db.refresh(profile)
        logger.info(f"Saved baseline profile {version} ({baseline_name}). Active={is_active}")
        return profile
