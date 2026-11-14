"""Quarantine Manager for isolating and tracking invalid and rejected records."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from app.config import settings
from app.models.database_models import RejectedRecord


class QuarantineManager:
    """Handles persistence of quarantined records to database and audit logs."""

    @staticmethod
    def quarantine_records(
        db: Session,
        run_id: str,
        source_file: str,
        rejected_items: List[Dict[str, Any]]
    ) -> int:
        """
        Persists invalid records to the rejected_records database table
        and writes a JSON audit file to DATA_REJECTED_DIR.
        """
        if not rejected_items:
            return 0

        now = datetime.now(timezone.utc)
        db_records: List[RejectedRecord] = []
        audit_payload: List[Dict[str, Any]] = []

        for item in rejected_items:
            line_no = item.get("line_number")
            raw_data_str = json.dumps(item.get("raw_data", {})) if isinstance(item.get("raw_data"), dict) else str(item.get("raw_data", ""))
            reason = item.get("reason", "Unknown validation error")
            code = item.get("code", "UNKNOWN_ERROR")

            rec = RejectedRecord(
                run_id=run_id,
                source_file=source_file,
                line_number=line_no,
                raw_data=raw_data_str,
                rejection_reason=reason,
                rejection_code=code,
                rejected_at=now,
            )
            db_records.append(rec)

            audit_payload.append({
                "run_id": run_id,
                "source_file": source_file,
                "line_number": line_no,
                "raw_data": item.get("raw_data"),
                "rejection_reason": reason,
                "rejection_code": code,
                "rejected_at": now.isoformat(),
            })

        # Save to database in bulk
        db.bulk_save_objects(db_records)
        db.flush()

        # Write audit file to disk
        try:
            rejected_dir = Path(settings.DATA_REJECTED_DIR)
            rejected_dir.mkdir(parents=True, exist_ok=True)
            audit_file = rejected_dir / f"{run_id}_rejected.json"
            with open(audit_file, "w", encoding="utf-8") as f:
                json.dump(audit_payload, f, indent=2)
        except Exception as e:
            # Audit log to disk is best effort; db record is guaranteed
            print(f"Warning: Failed to write quarantine audit file: {e}")

        return len(db_records)

    @staticmethod
    def get_rejected_records(
        db: Session,
        run_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[RejectedRecord]:
        """Fetch paginated rejected records, optionally filtered by run_id."""
        query = db.query(RejectedRecord)
        if run_id:
            query = query.filter(RejectedRecord.run_id == run_id)
        return query.order_by(RejectedRecord.id.desc()).offset(offset).limit(limit).all()

