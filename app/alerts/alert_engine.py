"""Explainable Anomaly Alert Engine comparing batch quality profiles against baselines."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database_models import DataQualityAlert, DataQualityProfile, BaselineProfile
from app.models.enums import AlertSeverity
from app.profiling.baseline import BaselineManager

logger = logging.getLogger("alert_engine")


class AlertEngine:
    """Evaluates data quality profiles against baseline profiles and generates explainable alerts."""

    @classmethod
    def evaluate_run(
        cls,
        db: Session,
        run_id: str,
        profile: DataQualityProfile,
        baseline: Optional[BaselineProfile] = None
    ) -> List[DataQualityAlert]:
        """Convenience wrapper for evaluate_batch."""
        return cls.evaluate_batch(db=db, profile=profile, baseline=baseline)

    @classmethod
    def evaluate_batch(
        cls,
        db: Session,
        profile: DataQualityProfile,
        baseline: Optional[BaselineProfile] = None
    ) -> List[DataQualityAlert]:
        """
        Compare current batch profile to baseline and generate alerts if thresholds are breached.
        Guarantees idempotent alert generation (no duplicate alerts for same run and metric).
        """
        if baseline is None:
            baseline = BaselineManager.get_active_baseline(db)

        if not baseline:
            logger.warning("No active baseline profile found for anomaly evaluation.")
            return []

        alerts: List[DataQualityAlert] = []
        now = datetime.now(timezone.utc)
        run_id = profile.run_id

        # 1. Volume Drop / Spike Evaluation
        if baseline.record_volume > 0:
            diff_volume = profile.batch_volume - baseline.record_volume
            pct_volume_change = (diff_volume / baseline.record_volume) * 100.0

            # Volume drop alert
            if pct_volume_change <= -abs(settings.ALERT_VOLUME_DROP_PCT):
                explanation = (
                    f"Batch volume of {profile.batch_volume} is {abs(pct_volume_change):.1f}% lower than "
                    f"expected baseline volume of {baseline.record_volume} records."
                )
                suggested_action = (
                    "Investigate upstream source systems and ingestion pipelines for missing partitions, "
                    "delayed file delivery, or upstream producer downtime."
                )
                severity = AlertSeverity.CRITICAL if abs(pct_volume_change) >= 60.0 else AlertSeverity.WARNING

                alert = cls._create_or_get_alert(
                    db=db,
                    run_id=run_id,
                    metric_name="record_volume",
                    baseline_val=float(baseline.record_volume),
                    current_val=float(profile.batch_volume),
                    diff=float(diff_volume),
                    pct_change=round(pct_volume_change, 2),
                    severity=severity.value,
                    explanation=explanation,
                    action=suggested_action,
                    created_at=now,
                )
                if alert:
                    alerts.append(alert)

            # Volume spike alert
            elif pct_volume_change >= settings.ALERT_VOLUME_SPIKE_PCT:
                explanation = (
                    f"Batch volume of {profile.batch_volume} surged by {pct_volume_change:.1f}% higher than "
                    f"expected baseline volume of {baseline.record_volume} records."
                )
                suggested_action = (
                    "Verify potential duplicate event flooding, marketing campaign surges, or upstream replay events."
                )
                severity = AlertSeverity.WARNING

                alert = cls._create_or_get_alert(
                    db=db,
                    run_id=run_id,
                    metric_name="record_volume_spike",
                    baseline_val=float(baseline.record_volume),
                    current_val=float(profile.batch_volume),
                    diff=float(diff_volume),
                    pct_change=round(pct_volume_change, 2),
                    severity=severity.value,
                    explanation=explanation,
                    action=suggested_action,
                    created_at=now,
                )
                if alert:
                    alerts.append(alert)

        # 2. Null Rate / Quarantine Rate Evaluation
        diff_null = profile.null_rate - baseline.null_rate
        # Difference in percentage points
        diff_null_pct_points = diff_null * 100.0

        if diff_null_pct_points >= settings.ALERT_NULL_RATE_INCREASE_PCT:
            explanation = (
                f"Batch null/rejection rate rose to {profile.null_rate * 100:.1f}%, an increase of "
                f"{diff_null_pct_points:.1f} percentage points over baseline of {baseline.null_rate * 100:.1f}%."
            )
            suggested_action = (
                "Review quarantined records in the rejected_records table and check upstream schema drift, "
                "missing mandatory fields, or malformed formats."
            )
            severity = AlertSeverity.CRITICAL if diff_null_pct_points >= 20.0 else AlertSeverity.WARNING

            alert = cls._create_or_get_alert(
                db=db,
                run_id=run_id,
                metric_name="null_rate",
                baseline_val=float(baseline.null_rate),
                current_val=float(profile.null_rate),
                diff=round(diff_null, 4),
                pct_change=round(diff_null_pct_points, 2),
                severity=severity.value,
                explanation=explanation,
                action=suggested_action,
                created_at=now,
            )
            if alert:
                alerts.append(alert)

        # 3. Mean Transaction Amount Drift
        if baseline.mean_amount > 0 and profile.mean_amount > 0:
            diff_amount = profile.mean_amount - baseline.mean_amount
            pct_amount_drift = (diff_amount / baseline.mean_amount) * 100.0

            if abs(pct_amount_drift) >= settings.ALERT_AMOUNT_DRIFT_PCT:
                direction = "higher" if pct_amount_drift > 0 else "lower"
                explanation = (
                    f"Mean transaction amount of ${profile.mean_amount:.2f} is {abs(pct_amount_drift):.1f}% "
                    f"{direction} than baseline of ${baseline.mean_amount:.2f}."
                )
                suggested_action = (
                    "Inspect transaction values for decimal scaling errors, currency mismatch, or outlier transactions."
                )
                severity = AlertSeverity.WARNING

                alert = cls._create_or_get_alert(
                    db=db,
                    run_id=run_id,
                    metric_name="mean_amount",
                    baseline_val=float(baseline.mean_amount),
                    current_val=float(profile.mean_amount),
                    diff=round(diff_amount, 2),
                    pct_change=round(pct_amount_drift, 2),
                    severity=severity.value,
                    explanation=explanation,
                    action=suggested_action,
                    created_at=now,
                )
                if alert:
                    alerts.append(alert)

        # 4. Freshness Violation Evaluation
        if profile.event_freshness_sec > settings.ALERT_FRESHNESS_MAX_SEC:
            freshness_diff = profile.event_freshness_sec - baseline.event_freshness_sec
            freshness_pct = (freshness_diff / baseline.event_freshness_sec * 100.0) if baseline.event_freshness_sec > 0 else 0.0
            explanation = (
                f"Batch event freshness of {profile.event_freshness_sec / 3600.0:.1f} hours exceeds "
                f"maximum allowable latency of {settings.ALERT_FRESHNESS_MAX_SEC / 3600.0:.1f} hours."
            )
            suggested_action = (
                "Verify upstream data delivery schedule and investigate pipeline backlog."
            )
            alert = cls._create_or_get_alert(
                db=db,
                run_id=run_id,
                metric_name="event_freshness",
                baseline_val=float(baseline.event_freshness_sec),
                current_val=float(profile.event_freshness_sec),
                diff=round(freshness_diff, 2),
                pct_change=round(freshness_pct, 2),
                severity=AlertSeverity.WARNING.value,
                explanation=explanation,
                action=suggested_action,
                created_at=now,
            )
            if alert:
                alerts.append(alert)

        db.commit()
        return alerts

    @staticmethod
    def _create_or_get_alert(
        db: Session,
        run_id: str,
        metric_name: str,
        baseline_val: float,
        current_val: float,
        diff: float,
        pct_change: float,
        severity: str,
        explanation: str,
        action: str,
        created_at: datetime,
    ) -> Optional[DataQualityAlert]:
        """Ensures deduplicated alert creation per run and metric."""
        existing = db.query(DataQualityAlert).filter_by(
            run_id=run_id, metric_name=metric_name
        ).first()

        if existing:
            return existing

        alert_id = f"alt_{uuid.uuid4().hex[:12]}"
        alert = DataQualityAlert(
            alert_id=alert_id,
            run_id=run_id,
            metric_name=metric_name,
            baseline_value=baseline_val,
            current_value=current_val,
            difference=diff,
            pct_change=pct_change,
            severity=severity,
            explanation=explanation,
            suggested_action=action,
            is_resolved=False,
            created_at=created_at,
        )
        db.add(alert)
        return alert

    @staticmethod
    def get_alerts(
        db: Session,
        run_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[DataQualityAlert]:
        """Query alerts with filtering by run_id or severity."""
        query = db.query(DataQualityAlert)
        if run_id:
            query = query.filter(DataQualityAlert.run_id == run_id)
        if severity:
            query = query.filter(DataQualityAlert.severity == severity.upper())
        return query.order_by(DataQualityAlert.created_at.desc()).offset(offset).limit(limit).all()
