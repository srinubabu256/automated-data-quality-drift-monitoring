"""Null-Rate Drift Detection Module for YottaFlex Data Quality Monitoring."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.enums import AlertSeverity, DetectionMethod, DriftType

logger = logging.getLogger("null_drift")


class NullRateDriftDetector:
    """Evaluates column-level null-rate anomalies comparing current batch against approved baseline."""

    @classmethod
    def evaluate_column(
        cls,
        column_name: str,
        current_null_count: int,
        current_total_rows: int,
        baseline_null_rate_pct: Optional[float],
        run_id: str = "RUN_ADHOC",
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
        warning_pp: Optional[float] = None,
        high_pp: Optional[float] = None,
        critical_pp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates null-rate drift for a single column.

        Formulas:
            null_rate_pct = (null_count / total_rows) * 100.0
            null_rate_change_pp = current_null_rate_pct - baseline_null_rate_pct
        """
        warn_pp = warning_pp if warning_pp is not None else settings.DRIFT_NULL_RATE_WARNING_PP
        hi_pp = high_pp if high_pp is not None else settings.DRIFT_NULL_RATE_HIGH_PP
        crit_pp = critical_pp if critical_pp is not None else settings.DRIFT_NULL_RATE_CRITICAL_PP

        # Zero-row division protection
        if current_total_rows == 0:
            current_null_rate_pct = 0.0
        else:
            current_null_rate_pct = (current_null_count / current_total_rows) * 100.0

        current_null_rate_pct = round(current_null_rate_pct, 4)

        if baseline_null_rate_pct is None:
            return {
                "run_id": run_id,
                "baseline_version": baseline_version,
                "drift_type": DriftType.NULL_RATE.value,
                "column_name": column_name,
                "detection_method": DetectionMethod.PERCENTAGE_POINT_SHIFT.value,
                "baseline_value": None,
                "current_value": current_null_rate_pct,
                "absolute_difference": None,
                "percentage_difference": None,
                "statistical_statistic": None,
                "p_value": None,
                "degrees_of_freedom": None,
                "drift_detected": False,
                "severity": "NONE",
                "configured_threshold": warn_pp,
                "details": f"No baseline null-rate provided for column '{column_name}'.",
                "alert": None,
            }

        diff_pp = round(current_null_rate_pct - baseline_null_rate_pct, 2)

        # Severity mapping based on percentage point shift
        if diff_pp >= crit_pp:
            severity = AlertSeverity.CRITICAL.value
            drift_detected = True
        elif diff_pp >= hi_pp:
            severity = AlertSeverity.HIGH.value
            drift_detected = True
        elif diff_pp >= warn_pp:
            severity = AlertSeverity.MEDIUM.value
            drift_detected = True
        elif diff_pp > 0:
            severity = AlertSeverity.LOW.value
            drift_detected = False
        else:
            severity = "NONE"
            drift_detected = False

        alert = None
        if drift_detected:
            explanation = (
                f"The '{column_name}' null rate increased from {baseline_null_rate_pct:.1f}% to "
                f"{current_null_rate_pct:.1f}% (+{diff_pp:.1f} percentage points), exceeding configured "
                f"threshold of {warn_pp:.1f} pp."
            )
            recommended_action = (
                f"Inspect upstream data ingestion for column '{column_name}'. Check for missing mandatory fields, "
                "schema drift, payload serialization failures, or upstream extraction filter changes."
            )

            alert = {
                "alert_id": f"alt_null_{column_name}_{uuid.uuid4().hex[:8]}",
                "batch_id": run_id,
                "run_id": run_id,
                "dataset_name": dataset_name,
                "column_name": column_name,
                "drift_type": DriftType.NULL_RATE.value,
                "metric_name": f"null_rate:{column_name}",
                "severity": severity,
                "baseline_value": float(baseline_null_rate_pct),
                "current_value": float(current_null_rate_pct),
                "absolute_difference": float(diff_pp),
                "percentage_difference": float(diff_pp),
                "detection_method": DetectionMethod.PERCENTAGE_POINT_SHIFT.value,
                "statistical_statistic": None,
                "p_value": None,
                "configured_threshold": float(warn_pp),
                "explanation": explanation,
                "recommended_action": recommended_action,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "run_id": run_id,
            "baseline_version": baseline_version,
            "drift_type": DriftType.NULL_RATE.value,
            "column_name": column_name,
            "detection_method": DetectionMethod.PERCENTAGE_POINT_SHIFT.value,
            "baseline_value": float(baseline_null_rate_pct),
            "current_value": float(current_null_rate_pct),
            "absolute_difference": float(diff_pp),
            "percentage_difference": float(diff_pp),
            "statistical_statistic": None,
            "p_value": None,
            "degrees_of_freedom": None,
            "drift_detected": drift_detected,
            "severity": severity,
            "configured_threshold": float(warn_pp),
            "details": f"Baseline null rate: {baseline_null_rate_pct:.2f}%, Current: {current_null_rate_pct:.2f}%, Shift: {diff_pp:+.2f} pp",
            "alert": alert,
        }

    @classmethod
    def evaluate_batch(
        cls,
        records: List[Dict[str, Any]],
        baseline_null_rates: Dict[str, float],
        run_id: str = "RUN_ADHOC",
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
        columns_to_evaluate: Optional[List[str]] = None,
        warning_pp: Optional[float] = None,
        high_pp: Optional[float] = None,
        critical_pp: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Evaluates null-rate drift across all specified or discovered columns in batch.
        """
        total_rows = len(records)
        if columns_to_evaluate is None:
            # Discover columns from records and baseline
            found_cols = set()
            for r in records:
                found_cols.update(r.keys())
            found_cols.update(baseline_null_rates.keys())
            target_cols = sorted(list(found_cols))
        else:
            target_cols = columns_to_evaluate

        results = []
        for col in target_cols:
            null_count = 0
            for r in records:
                val = r.get(col)
                if val is None or str(val).strip() == "" or str(val).lower() == "nan":
                    null_count += 1

            b_rate = baseline_null_rates.get(col)
            res = cls.evaluate_column(
                column_name=col,
                current_null_count=null_count,
                current_total_rows=total_rows,
                baseline_null_rate_pct=b_rate,
                run_id=run_id,
                baseline_version=baseline_version,
                dataset_name=dataset_name,
                warning_pp=warning_pp,
                high_pp=high_pp,
                critical_pp=critical_pp,
            )
            results.append(res)

        return results
