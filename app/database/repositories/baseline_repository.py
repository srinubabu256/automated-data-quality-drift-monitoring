"""Repository for baseline profiles and historical reference versions."""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import BaselineProfile


class BaselineRepository:
    """Encapsulates database operations for baseline profiles."""

    @staticmethod
    def get_active(db: Session, version: Optional[str] = None) -> Optional[BaselineProfile]:
        target_version = version or settings.BASELINE_VERSION
        profile = db.query(BaselineProfile).filter_by(version=target_version).first()
        if not profile:
            profile = db.query(BaselineProfile).filter_by(is_active=True).order_by(BaselineProfile.id.desc()).first()
        return profile

    @staticmethod
    def list_all(db: Session) -> List[BaselineProfile]:
        return db.query(BaselineProfile).order_by(BaselineProfile.id.desc()).all()
