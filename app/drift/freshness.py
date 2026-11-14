"""Freshness Drift Detection Module for YottaFlex Platform."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database.enums import AlertSeverity, DetectionMethod, DriftType

logger = logging.getLogger("drift.freshness")


class FreshnessDriftDetector:
    """Evaluates event-time freshness and ingestion latency shifts against baseline thresholds."""

    @classmethod
    def evaluate(
        cls,
        current_freshness_sec: float,
        baseline_freshness_sec: Optional[float] = None,
        run_id: str = "RUN_ADHOC",
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
        warning_multiplier: float = 2.0,
        critical_multiplier: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Evaluates event freshness latency against baseline freshness latency.
        Generates alerts if batch latency significantly exceeds baseline SLA.
        """
        base_sec = baseline_freshness_sec if baseline_freshness_sec is not None else settings.BASELINE_EVENT_FRESHNESS_SEC
        if base_sec <= 0:
            base_sec = 3600.0

        ratio = current_freshness_sec / base_sec
        diff_sec = current_freshness_sec - base_sec
        pct_change = (diff_sec / base_sec) * 100.0

        if ratio >= critical_multiplier:
            drift_detected = True
            severity = AlertSeverity.CRITICAL.value
        elif ratio >= warning_multiplier:
            drift_detected = True
            severity = AlertSeverity.WARNING.value
        else:
            drift_detected = False
            severity = "NONE"

        alert = None
        if drift_detected:
            explanation = (
                f"Batch event freshness latency of {current_freshness_sec:.1f}s is {ratio:.1f}x higher than "
                f"expected baseline SLA of {base_sec:.1f}s (+{pct_change:.1f}% lag shift)."
            )
            recommended_action = (
                "Investigate upstream ingestion delays, message broker queue buildup, or producer clock skew."
            )

            alert = {
                "alert_id": f"alt_fresh_{uuid.uuid4().hex[:8]}",
                "batch_id": run_id,
                "run_id": run_id,
                "dataset_name": dataset_name,
                "column_name": "event_timestamp",
                "drift_type": DriftType.FRESHNESS.value,
                "metric_name": "freshness:event_latency",
                "severity": severity,
                "baseline_value": float(base_sec),
                "current_value": float(current_freshness_sec),
                "absolute_difference": round(float(diff_sec), 2),
                "percentage_difference": round(float(pct_change), 2),
                "detection_method": DetectionMethod.LATENCY_SHIFT.value,
                "statistical_statistic": round(ratio, 2),
                "p_value": None,
                "configured_threshold": float(base_sec * warning_multiplier),
                "explanation": explanation,
                "recommended_action": recommended_action,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "run_id": run_id,
            "baseline_version": baseline_version,
            "drift_type": DriftType.FRESHNESS.value,
            "column_name": "event_timestamp",
            "detection_method": DetectionMethod.LATENCY_SHIFT.value,
            "baseline_value": float(base_sec),
            "current_value": float(current_freshness_sec),
            "absolute_difference": round(float(diff_sec), 2),
            "percentage_difference": round(float(pct_change), 2),
            "drift_detected": drift_detected,
            "severity": severity,
            "details": f"Baseline: {base_sec:.1f}s, Current: {current_freshness_sec:.1f}s (Ratio: {ratio:.2f}x)",
            "alert": alert,
        }
