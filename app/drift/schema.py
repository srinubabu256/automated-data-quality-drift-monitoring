"""Schema Drift Detection Module for YottaFlex Platform."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.database.enums import AlertSeverity, DetectionMethod, DriftType

logger = logging.getLogger("drift.schema")


class SchemaDriftDetector:
    """Evaluates structural and syntactic schema drift comparing batch columns against baseline."""

    STANDARD_COLUMNS: Set[str] = {
        "event_id",
        "transaction_id",
        "customer_id",
        "product_id",
        "event_type",
        "amount",
        "currency",
        "event_timestamp",
    }

    @classmethod
    def evaluate(
        cls,
        current_columns: List[str],
        baseline_columns: Optional[List[str]] = None,
        run_id: str = "RUN_ADHOC",
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
    ) -> Dict[str, Any]:
        """Detects missing required columns or unexpected additional columns."""
        expected = set(baseline_columns) if baseline_columns else cls.STANDARD_COLUMNS
        current = set(current_columns)

        missing_cols = sorted(list(expected - current))
        added_cols = sorted(list(current - expected))

        drift_detected = len(missing_cols) > 0 or len(added_cols) > 0
        severity = AlertSeverity.CRITICAL.value if missing_cols else (
            AlertSeverity.WARNING.value if added_cols else "NONE"
        )

        alert = None
        if drift_detected:
            parts = []
            if missing_cols:
                parts.append(f"Missing mandatory columns: {missing_cols}")
            if added_cols:
                parts.append(f"Unexpected new columns: {added_cols}")
            explanation = f"Schema drift detected in batch: {'; '.join(parts)}."
            recommended_action = (
                "Verify upstream contract definition, schema evolution registry, or data provider serialization."
            )

            alert = {
                "alert_id": f"alt_schema_{uuid.uuid4().hex[:8]}",
                "batch_id": run_id,
                "run_id": run_id,
                "dataset_name": dataset_name,
                "column_name": None,
                "drift_type": DriftType.SCHEMA.value,
                "metric_name": "schema:column_drift",
                "severity": severity,
                "baseline_value": float(len(expected)),
                "current_value": float(len(current)),
                "absolute_difference": float(len(added_cols) - len(missing_cols)),
                "percentage_difference": round(float((len(current) - len(expected)) / len(expected) * 100.0), 2) if expected else 0.0,
                "detection_method": DetectionMethod.SCHEMA_DIFF.value,
                "statistical_statistic": float(len(missing_cols) + len(added_cols)),
                "p_value": None,
                "configured_threshold": 0.0,
                "explanation": explanation,
                "recommended_action": recommended_action,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        return {
            "run_id": run_id,
            "baseline_version": baseline_version,
            "drift_type": DriftType.SCHEMA.value,
            "column_name": None,
            "detection_method": DetectionMethod.SCHEMA_DIFF.value,
            "expected_columns": sorted(list(expected)),
            "current_columns": sorted(list(current)),
            "missing_columns": missing_cols,
            "added_columns": added_cols,
            "drift_detected": drift_detected,
            "severity": severity,
            "details": f"Missing: {len(missing_cols)}, Added: {len(added_cols)}",
            "alert": alert,
        }
