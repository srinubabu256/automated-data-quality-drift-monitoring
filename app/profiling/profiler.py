"""Data quality profiler generating statistical summaries and distributions."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.database_models import DataQualityProfile, ProcessingRun, RawEvent
from app.profiling.distribution import DistributionCalculator


class Profiler:
    """Computes and stores statistical data quality profiles for batches."""

    @classmethod
    def create_batch_profile(
        cls,
        db: Session,
        run_id: str,
        rows: List[Dict[str, Any]],
        accepted_items: List[Dict[str, Any]],
        rejected_items: List[Dict[str, Any]],
    ) -> DataQualityProfile:
        """
        Creates or updates a DataQualityProfile record for the run.
        """
        batch_volume = len(rows)
        null_rate = float(len(rejected_items)) / float(batch_volume) if batch_volume > 0 else 0.0

        # Extract amounts from accepted items
        amounts: List[float] = []
        latest_ts: Optional[datetime] = None

        for item in accepted_items:
            d = item.get("data", {})
            amt = d.get("amount")
            if amt is not None:
                try:
                    amounts.append(float(amt))
                except (ValueError, TypeError):
                    pass

            ts = d.get("event_timestamp")
            if ts:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts

        # Descriptive statistics
        summary = DistributionCalculator.calculate_numeric_summary(amounts)

        now = datetime.now(timezone.utc)
        freshness_sec = 0.0
        if latest_ts:
            freshness_sec = max(0.0, (now - latest_ts).total_seconds())

        profile = db.query(DataQualityProfile).filter_by(run_id=run_id).first()
        if not profile:
            profile = DataQualityProfile(
                run_id=run_id,
                batch_volume=batch_volume,
                null_rate=round(null_rate, 4),
                mean_amount=summary["mean"],
                std_amount=summary["std"],
                min_amount=summary["min"],
                max_amount=summary["max"],
                median_amount=summary["median"],
                p95_amount=summary["p95"],
                event_freshness_sec=round(freshness_sec, 2),
                created_at=now,
            )
            db.add(profile)
        else:
            profile.batch_volume = batch_volume
            profile.null_rate = round(null_rate, 4)
            profile.mean_amount = summary["mean"]
            profile.std_amount = summary["std"]
            profile.min_amount = summary["min"]
            profile.max_amount = summary["max"]
            profile.median_amount = summary["median"]
            profile.p95_amount = summary["p95"]
            profile.event_freshness_sec = round(freshness_sec, 2)

        db.commit()
        db.refresh(profile)
        return profile

    @classmethod
    def profile_run(
        cls,
        db: Session,
        run_id: str,
        amounts: Optional[List[float]] = None
    ) -> DataQualityProfile:
        """Alias for profiling when only run_id is passed."""
        run = db.query(ProcessingRun).filter_by(run_id=run_id).first()
        if not run:
            raise ValueError(f"ProcessingRun {run_id} not found.")

        if amounts is None:
            raw_amounts = (
                db.query(RawEvent.amount)
                .filter(RawEvent.run_id == run_id, RawEvent.amount.isnot(None))
                .all()
            )
            amounts = [float(r[0]) for r in raw_amounts if r[0] is not None]

        summary = DistributionCalculator.calculate_numeric_summary(amounts)
        total_items = run.input_count
        null_rate = float(run.rejected_count) / float(total_items) if total_items > 0 else 0.0

        now = datetime.now(timezone.utc)
        latest_event = (
            db.query(RawEvent.event_timestamp)
            .filter_by(run_id=run_id)
            .order_by(RawEvent.event_timestamp.desc())
            .first()
        )
        freshness_sec = 0.0
        if latest_event and latest_event[0]:
            ts = latest_event[0]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            freshness_sec = max(0.0, (now - ts).total_seconds())

        profile = db.query(DataQualityProfile).filter_by(run_id=run_id).first()
        if not profile:
            profile = DataQualityProfile(
                run_id=run_id,
                batch_volume=run.input_count,
                null_rate=round(null_rate, 4),
                mean_amount=summary["mean"],
                std_amount=summary["std"],
                min_amount=summary["min"],
                max_amount=summary["max"],
                median_amount=summary["median"],
                p95_amount=summary["p95"],
                event_freshness_sec=round(freshness_sec, 2),
                created_at=now,
            )
            db.add(profile)
        else:
            profile.batch_volume = run.input_count
            profile.null_rate = round(null_rate, 4)
            profile.mean_amount = summary["mean"]
            profile.std_amount = summary["std"]
            profile.min_amount = summary["min"]
            profile.max_amount = summary["max"]
            profile.median_amount = summary["median"]
            profile.p95_amount = summary["p95"]
            profile.event_freshness_sec = round(freshness_sec, 2)

        db.commit()
        db.refresh(profile)
        return profile


# Backward-compatible alias
BatchProfiler = Profiler
