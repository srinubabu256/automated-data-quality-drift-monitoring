"""Unit tests for Freshness and Schema Drift modules."""
import pytest
from app.drift.freshness import FreshnessDriftDetector
from app.drift.schema import SchemaDriftDetector
from app.database.enums import AlertSeverity, DriftType


def test_freshness_drift_normal():
    res = FreshnessDriftDetector.evaluate(
        current_freshness_sec=3600.0,
        baseline_freshness_sec=3600.0,
        run_id="RUN_FRESH_NORMAL",
    )
    assert res["drift_detected"] is False
    assert res["severity"] == "NONE"
    assert res["alert"] is None


def test_freshness_drift_spike():
    # 25,000s vs 3,600s baseline (> 5x multiplier -> CRITICAL)
    res = FreshnessDriftDetector.evaluate(
        current_freshness_sec=25000.0,
        baseline_freshness_sec=3600.0,
        run_id="RUN_FRESH_SPIKE",
    )
    assert res["drift_detected"] is True
    assert res["severity"] == AlertSeverity.CRITICAL.value
    assert res["alert"] is not None
    assert "freshness latency" in res["alert"]["explanation"]


def test_schema_drift_no_drift():
    std_cols = [
        "event_id", "transaction_id", "customer_id", "product_id",
        "event_type", "amount", "currency", "event_timestamp"
    ]
    res = SchemaDriftDetector.evaluate(current_columns=std_cols)
    assert res["drift_detected"] is False
    assert res["severity"] == "NONE"


def test_schema_drift_missing_and_added_columns():
    cols = ["event_id", "transaction_id", "amount", "new_feature_col"]
    res = SchemaDriftDetector.evaluate(current_columns=cols)
    assert res["drift_detected"] is True
    assert "new_feature_col" in res["added_columns"]
    assert "customer_id" in res["missing_columns"]
    assert res["severity"] == AlertSeverity.CRITICAL.value
    assert res["alert"] is not None
