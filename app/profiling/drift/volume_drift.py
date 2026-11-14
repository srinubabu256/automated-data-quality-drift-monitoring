"""Volume Drift Detection Module for YottaFlex Data Quality Monitoring."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import settings
from app.models.enums import AlertSeverity, DetectionMethod, DriftType

logger = logging.getLogger("volume_drift")


class VolumeDriftDetector:
    """Evaluates volume drift between approved baseline record volume and incoming batch volume."""

    @classmethod
    def evaluate(
        cls,
        current_count: int,
        baseline_count: Optional[int],
        run_id: str = "RUN_ADHOC",
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
        warning_pct: Optional[float] = None,
        critical_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculates volume drift and produces structured metrics and explainable alerts.

        Formula:
            volume_change_pct = ((current_count - baseline_count) / baseline_count) * 100.0
        """
        warn_thresh = warning_pct if warning_pct is not None else settings.DRIFT_VOLUME_WARNING_PCT
        crit_thresh = critical_pct if critical_pct is not None else settings.DRIFT_VOLUME_CRITICAL_PCT

        # Handle missing baseline
        if baseline_count is None:
            logger.warning(f"No baseline volume found for run {run_id}.")
            return {
                "run_id": run_id,
                "baseline_version": baseline_version,
                "drift_type": DriftType.VOLUME.value,
                "column_name": None,
                "detection_method": DetectionMethod.PERCENTAGE_CHANGE.value,
                "baseline_value": None,
                "current_value": float(current_count),
                "absolute_difference": None,
                "percentage_difference": None,
                "statistical_statistic": None,
                "p_value": None,
                "degrees_of_freedom": None,
                "drift_detected": False,
                "severity": "NONE",
                "configured_threshold": warn_thresh,
                "details": "Baseline volume not provided or missing.",
                "alert": None,
            }

        # Handle zero baseline volume
        if baseline_count == 0:
            if current_count == 0:
                pct_change = 0.0
                diff = 0
                drift_detected = False
                severity = "NONE"
            else:
                pct_change = 100.0
                diff = current_count
                drift_detected = True
                severity = AlertSeverity.CRITICAL.value
        else:
            diff = current_count - baseline_count
            pct_change = (diff / baseline_count) * 100.0

            # Severity mapping based on configurable thresholds
            abs_pct = abs(pct_change)
            if abs_pct >= crit_thresh:
                severity = AlertSeverity.CRITICAL.value
                drift_detected = True
            elif abs_pct >= warn_thresh:
                severity = AlertSeverity.HIGH.value if pct_change < 0 else AlertSeverity.WARNING.value
                drift_detected = True
            else:
                severity = "NONE"
                drift_detected = False

        alert = None
        if drift_detected:
            if pct_change < 0:
                direction = "lower than"
                explanation = (
                    f"Batch volume of {current_count} is {abs(pct_change):.1f}% {direction} expected "
                    f"baseline volume of {baseline_count} records (threshold: -{warn_thresh:.1f}%)."
                )
                recommended_action = (
                    "Investigate upstream source systems and ingestion pipelines for missing partitions, "
                    "delayed file delivery, or upstream producer downtime."
                )
            else:
                direction = "higher than"
                explanation = (
                    f"Batch volume of {current_count} surged by {pct_change:.1f}% {direction} expected "
                    f"baseline volume of {baseline_count} records (threshold: +{warn_thresh:.1f}%)."
                )
                recommended_action = (
                    "Verify potential duplicate event flooding, marketing campaign surges, "
                    "or upstream replay/retransmission events."
                )

            alert = {
                "alert_id": f"alt_vol_{uuid.uuid4().hex[:12]}",
                "batch_id": run_id,
                "run_id": run_id,
                "dataset_name": dataset_name,
                "column_name": None,
                "drift_type": DriftType.VOLUME.value,
                "metric_name": "record_volume",
                "severity": severity,
                "baseline_value": float(baseline_count),
                "current_value": float(current_count),
                "absolute_difference": float(diff),
                "percentage_difference": round(float(pct_change), 2),
                "detection_method": DetectionMethod.PERCENTAGE_CHANGE.value,
                "statistical_statistic": None,
                "p_value": None,
                "configured_threshold": float(crit_thresh if severity == AlertSeverity.CRITICAL.value else warn_thresh),
                "explanation": explanation,
                "recommended_action": recommended_action,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "run_id": run_id,
            "baseline_version": baseline_version,
            "drift_type": DriftType.VOLUME.value,
            "column_name": None,
            "detection_method": DetectionMethod.PERCENTAGE_CHANGE.value,
            "baseline_value": float(baseline_count),
            "current_value": float(current_count),
            "absolute_difference": float(diff),
            "percentage_difference": round(float(pct_change), 2),
            "statistical_statistic": None,
            "p_value": None,
            "degrees_of_freedom": None,
            "drift_detected": drift_detected,
            "severity": severity,
            "configured_threshold": float(warn_thresh),
            "details": f"Baseline: {baseline_count}, Current: {current_count}, Change: {pct_change:.2f}%",
            "alert": alert,
        }
