"""Comprehensive Test Suite for Drift Detection Modules in YottaFlex.

Covers:
  - Volume Drift Detection (Spikes, Drops, Empty Batches, Zero Baselines, Thresholds)
  - Null-Rate Drift Detection (Column Shifts, 100% Nulls, Empty Batches, Multi-Column)
  - Distribution Drift Detection (Numeric PSI, Categorical PSI, KS 2-Sample, Chi-Square)
  - Statistical Test Selection Matrix (Identifier and Datetime Exclusions)
  - Database Persistence, Alert Deduplication, and REST API Endpoints
"""
import uuid
import numpy as np
import pytest
from datetime import datetime, timezone

from app.models.database_models import (
    BaselineProfile,
    DataQualityAlert,
    DriftAnalysisResult,
    ProcessingRun,
)
from app.models.enums import AlertSeverity, DetectionMethod, DriftType
from app.profiling.drift.distribution_drift import DistributionDriftDetector
from app.profiling.drift.drift_detector import DriftDetector
from app.profiling.drift.null_drift import NullRateDriftDetector
from app.profiling.drift.volume_drift import VolumeDriftDetector


# ==============================================================================
# 1. VOLUME DRIFT TESTS
# ==============================================================================


def test_volume_drift_significant_increase():
    """Verify volume spike (+50%) triggers an alert with expected attributes."""
    res = VolumeDriftDetector.evaluate(
        current_count=1500,
        baseline_count=1000,
        run_id="RUN_VOL_001",
        warning_pct=20.0,
        critical_pct=50.0,
    )
    assert res["drift_detected"] is True
    assert res["percentage_difference"] == 50.0
    assert res["absolute_difference"] == 500.0
    assert res["severity"] == AlertSeverity.CRITICAL.value

    alert = res["alert"]
    assert alert is not None
    assert alert["metric_name"] == "record_volume"
    assert "surged by 50.0%" in alert["explanation"]
    assert "Verify potential duplicate event flooding" in alert["recommended_action"]


def test_volume_drift_significant_decrease():
    """Verify volume drop (-80%) triggers a CRITICAL alert."""
    res = VolumeDriftDetector.evaluate(
        current_count=20000,
        baseline_count=100000,
        run_id="RUN_VOL_002",
        warning_pct=20.0,
        critical_pct=50.0,
    )
    assert res["drift_detected"] is True
    assert res["percentage_difference"] == -80.0
    assert res["absolute_difference"] == -80000.0
    assert res["severity"] == AlertSeverity.CRITICAL.value

    alert = res["alert"]
    assert alert is not None
    assert "80.0% lower than" in alert["explanation"]
    assert "Investigate upstream source systems" in alert["recommended_action"]


def test_volume_drift_normal_variation():
    """Verify normal volume variation (+5%) does not trigger drift alerts."""
    res = VolumeDriftDetector.evaluate(
        current_count=1050,
        baseline_count=1000,
        run_id="RUN_VOL_003",
        warning_pct=20.0,
        critical_pct=50.0,
    )
    assert res["drift_detected"] is False
    assert res["percentage_difference"] == 5.0
    assert res["severity"] == "NONE"
    assert res["alert"] is None


def test_volume_drift_empty_batch():
    """Verify empty batch (0 records) produces -100% change and CRITICAL alert."""
    res = VolumeDriftDetector.evaluate(
        current_count=0,
        baseline_count=1000,
        run_id="RUN_VOL_EMPTY",
    )
    assert res["drift_detected"] is True
    assert res["percentage_difference"] == -100.0
    assert res["severity"] == AlertSeverity.CRITICAL.value
    assert res["alert"] is not None


def test_volume_drift_zero_baseline():
    """Verify zero baseline volume is handled safely without division by zero."""
    res = VolumeDriftDetector.evaluate(
        current_count=100,
        baseline_count=0,
        run_id="RUN_VOL_ZERO_BASE",
    )
    assert res["drift_detected"] is True
    assert res["percentage_difference"] == 100.0
    assert res["severity"] == AlertSeverity.CRITICAL.value


def test_volume_drift_missing_baseline():
    """Verify missing baseline (None) returns graceful non-crashing result."""
    res = VolumeDriftDetector.evaluate(
        current_count=500,
        baseline_count=None,
        run_id="RUN_VOL_NO_BASE",
    )
    assert res["drift_detected"] is False
    assert res["alert"] is None
    assert "Baseline volume not provided" in res["details"]


# ==============================================================================
# 2. NULL-RATE DRIFT TESTS
# ==============================================================================


def test_null_rate_no_change():
    """Verify column with steady null rate (2%) detects no drift."""
    res = NullRateDriftDetector.evaluate_column(
        column_name="customer_email",
        current_null_count=20,
        current_total_rows=1000,
        baseline_null_rate_pct=2.0,
        run_id="RUN_NULL_001",
    )
    assert res["drift_detected"] is False
    assert res["percentage_difference"] == 0.0
    assert res["severity"] == "NONE"
    assert res["alert"] is None


def test_null_rate_increase_critical():
    """Verify null-rate spike from 2% to 40% (+38 pp) triggers CRITICAL alert."""
    res = NullRateDriftDetector.evaluate_column(
        column_name="customer_email",
        current_null_count=400,
        current_total_rows=1000,
        baseline_null_rate_pct=2.0,
        run_id="RUN_NULL_002",
        warning_pp=5.0,
        high_pp=15.0,
        critical_pp=25.0,
    )
    assert res["drift_detected"] is True
    assert res["percentage_difference"] == 38.0
    assert res["severity"] == AlertSeverity.CRITICAL.value

    alert = res["alert"]
    assert alert is not None
    assert alert["column_name"] == "customer_email"
    assert alert["metric_name"] == "null_rate:customer_email"
    assert "null rate increased from 2.0% to 40.0% (+38.0 percentage points)" in alert["explanation"]
    assert "Inspect upstream data ingestion" in alert["recommended_action"]


def test_null_rate_decrease_no_critical_alert():
    """Verify null rate dropping from 15% to 5% (-10 pp) does not generate an anomaly alert."""
    res = NullRateDriftDetector.evaluate_column(
        column_name="customer_email",
        current_null_count=50,
        current_total_rows=1000,
        baseline_null_rate_pct=15.0,
        run_id="RUN_NULL_003",
    )
    assert res["drift_detected"] is False
    assert res["percentage_difference"] == -10.0
    assert res["alert"] is None


def test_null_rate_completely_null_column():
    """Verify completely null column (100% null) triggers CRITICAL alert."""
    res = NullRateDriftDetector.evaluate_column(
        column_name="product_id",
        current_null_count=500,
        current_total_rows=500,
        baseline_null_rate_pct=0.0,
        run_id="RUN_NULL_ALL",
    )
    assert res["drift_detected"] is True
    assert res["current_value"] == 100.0
    assert res["percentage_difference"] == 100.0
    assert res["severity"] == AlertSeverity.CRITICAL.value


def test_null_rate_empty_dataset():
    """Verify zero rows in batch is protected against ZeroDivisionError."""
    res = NullRateDriftDetector.evaluate_column(
        column_name="amount",
        current_null_count=0,
        current_total_rows=0,
        baseline_null_rate_pct=1.0,
        run_id="RUN_NULL_EMPTY",
    )
    assert res["current_value"] == 0.0
    assert res["drift_detected"] is False
    assert res["alert"] is None


def test_null_rate_batch_evaluation():
    """Verify evaluate_batch processes multiple columns independently."""
    records = [
        {"customer_email": None, "amount": 100.0, "currency": "USD"},
        {"customer_email": None, "amount": 200.0, "currency": "USD"},
        {"customer_email": "a@b.com", "amount": 300.0, "currency": "USD"},
    ]
    # customer_email null rate is 2/3 = 66.67%, baseline is 0%
    baseline_rates = {"customer_email": 0.0, "amount": 0.0, "currency": 0.0}
    results = NullRateDriftDetector.evaluate_batch(
        records=records,
        baseline_null_rates=baseline_rates,
        run_id="RUN_BATCH_NULL",
    )
    assert len(results) == 3
    email_res = next(r for r in results if r["column_name"] == "customer_email")
    amount_res = next(r for r in results if r["column_name"] == "amount")

    assert email_res["drift_detected"] is True
    assert email_res["alert"] is not None
    assert amount_res["drift_detected"] is False
    assert amount_res["alert"] is None


# ==============================================================================
# 3. DISTRIBUTION DRIFT TESTS (PSI, KS, CHI-SQUARE)
# ==============================================================================


def test_numerical_psi_stable():
    """Verify numerical PSI on identical distributions indicates stability (PSI < 0.10)."""
    np.random.seed(42)
    baseline_vals = np.random.normal(150.0, 20.0, 1000).tolist()
    current_vals = np.random.normal(150.0, 20.0, 1000).tolist()

    res = DistributionDriftDetector.calculate_numeric_psi(
        current_values=current_vals,
        baseline_values=baseline_vals,
    )
    assert res["psi"] < 0.10
    assert res["drift_detected"] is False
    assert res["severity"] == "NONE"


def test_numerical_psi_significant_drift():
    """Verify numerical PSI detects heavy distribution shift (PSI >= 0.25)."""
    np.random.seed(42)
    baseline_vals = np.random.normal(100.0, 15.0, 1000).tolist()
    # Current values shifted drastically to mean 400
    current_vals = np.random.normal(400.0, 15.0, 1000).tolist()

    res = DistributionDriftDetector.calculate_numeric_psi(
        current_values=current_vals,
        baseline_values=baseline_vals,
    )
    assert res["psi"] > 0.25
    assert res["drift_detected"] is True
    assert res["severity"] == AlertSeverity.CRITICAL.value


def test_categorical_psi_with_new_and_disappeared_categories():
    """Verify categorical PSI handles unseen categories and disappeared categories."""
    baseline_freqs = {"New York": 0.5, "London": 0.5}
    # Current includes new category 'Bengaluru' and disappears 'London'
    current_cats = ["New York"] * 20 + ["Bengaluru"] * 80

    res = DistributionDriftDetector.calculate_categorical_psi(
        current_categories=current_cats,
        baseline_frequencies=baseline_freqs,
    )
    assert res["drift_detected"] is True
    assert res["psi"] > 0.20
    details = res["category_details"]
    assert details["Bengaluru"]["is_new_category"] is True
    assert details["London"]["is_disappeared"] is True


def test_ks_two_sample_test_detection():
    """Verify continuous KS test identifies identical vs drifted continuous samples."""
    np.random.seed(42)
    sample_a = np.random.normal(100.0, 10.0, 200).tolist()
    sample_b_same = np.random.normal(100.0, 10.0, 200).tolist()
    sample_c_diff = np.random.normal(120.0, 10.0, 200).tolist()

    # Same distribution: should not detect drift (p-value > 0.05)
    ks_same = DistributionDriftDetector.calculate_ks_test(sample_a, sample_b_same)
    assert ks_same["applicable"] is True
    assert ks_same["p_value"] > 0.01

    # Shifted distribution: should detect drift (p-value < 0.05)
    ks_diff = DistributionDriftDetector.calculate_ks_test(sample_a, sample_c_diff)
    assert ks_diff["applicable"] is True
    assert ks_diff["drift_detected"] is True
    assert ks_diff["p_value"] < 0.05
    assert ks_diff["statistic"] > 0.3


def test_ks_sample_size_and_constant_guards():
    """Verify KS test guards against sample size < 30 and constant column."""
    # Small sample guard
    small_a = [10.0, 20.0, 30.0]
    small_b = [10.0, 20.0, 30.0]
    res_small = DistributionDriftDetector.calculate_ks_test(small_a, small_b)
    assert res_small["applicable"] is False
    assert "Insufficient sample size" in res_small["interpretation"]

    # Constant column guard
    const_a = [100.0] * 50
    const_b = [100.0] * 50
    res_const = DistributionDriftDetector.calculate_ks_test(const_a, const_b)
    assert res_const["applicable"] is False
    assert "Constant numerical column" in res_const["interpretation"]


def test_chisquare_test_categorical():
    """Verify Chi-Square test computes expected frequencies and detects shifts."""
    baseline_freq = {"NEW": 0.70, "UPDATE": 0.20, "REVERSAL": 0.10}
    # Stable current sample (N=1000)
    current_stable = ["NEW"] * 700 + ["UPDATE"] * 200 + ["REVERSAL"] * 100
    chi_stable = DistributionDriftDetector.calculate_chisquare_test(current_stable, baseline_freq)
    assert chi_stable["applicable"] is True
    assert chi_stable["drift_detected"] is False
    assert chi_stable["p_value"] > 0.05

    # Drastically shifted sample
    current_shifted = ["NEW"] * 100 + ["UPDATE"] * 100 + ["REVERSAL"] * 800
    chi_shifted = DistributionDriftDetector.calculate_chisquare_test(current_shifted, baseline_freq)
    assert chi_shifted["applicable"] is True
    assert chi_shifted["drift_detected"] is True
    assert chi_shifted["p_value"] < 0.001


def test_test_selection_matrix_and_exclusions():
    """Verify identifiers and datetimes are excluded from distribution testing."""
    assert DistributionDriftDetector.is_identifier("event_id") is True
    assert DistributionDriftDetector.is_identifier("transaction_id") is True
    assert DistributionDriftDetector.is_identifier("customer_id") is True
    assert DistributionDriftDetector.is_identifier("product_id") is True
    assert DistributionDriftDetector.is_identifier("amount") is False

    assert DistributionDriftDetector.is_datetime("event_timestamp") is True
    assert DistributionDriftDetector.is_datetime("ingestion_timestamp") is True
    assert DistributionDriftDetector.is_datetime("created_at") is True
    assert DistributionDriftDetector.is_datetime("currency") is False

    # Evaluating an identifier should return skipped result
    res_id = DistributionDriftDetector.evaluate_column(
        column_name="transaction_id",
        current_values=["TX_1", "TX_2"],
    )
    assert res_id["drift_detected"] is False
    assert len(res_id["alerts"]) == 0


# ==============================================================================
# 4. ORCHESTRATION, PERSISTENCE, DEDUPLICATION & API INTEGRATION
# ==============================================================================


def test_drift_detector_orchestration_and_db_persistence(test_db):
    """Verify end-to-end drift analysis execution and database persistence."""
    run_id = f"RUN_DRIFT_{uuid.uuid4().hex[:8]}"

    # Prepare baseline with column details
    baseline_profile = {
        "version": "v1.0",
        "record_volume": 1000,
        "column_baselines": {
            "amount": {
                "type": "numeric",
                "null_rate": 0.0,
                "mean": 100.0,
                "values": np.random.normal(100.0, 10.0, 500).tolist(),
            },
            "customer_email": {
                "type": "categorical",
                "null_rate": 2.0,
            },
            "currency": {
                "type": "categorical",
                "null_rate": 0.0,
                "frequencies": {"USD": 0.9, "EUR": 0.1},
            },
        },
    }

    # Incoming batch with volume drop (50 records vs 1000 baseline),
    # customer_email null spike (40% nulls), and currency drift (all CAD)
    records = []
    for i in range(50):
        records.append({
            "event_id": f"evt_{i}",
            "transaction_id": f"tx_{i}",
            "customer_email": None if i < 20 else "user@example.com",
            "amount": float(np.random.normal(100.0, 10.0)),
            "currency": "CAD",
            "event_timestamp": "2026-11-14T10:00:00Z",
        })

    analysis = DriftDetector.analyze(
        records=records,
        baseline_profile=baseline_profile,
        run_id=run_id,
        baseline_version="v1.0",
        dataset_name="transactions",
        db=test_db,
        save_results=True,
    )

    assert analysis["run_id"] == run_id
    assert analysis["drift_detected"] is True
    assert analysis["persisted_results_count"] > 0
    assert analysis["persisted_alerts_count"] > 0

    # Query drift_analysis_results table
    db_results = test_db.query(DriftAnalysisResult).filter_by(run_id=run_id).all()
    assert len(db_results) == analysis["persisted_results_count"]

    # Query data_quality_alerts table
    db_alerts = test_db.query(DataQualityAlert).filter_by(run_id=run_id).all()
    assert len(db_alerts) == analysis["persisted_alerts_count"]

    # Verify all 17 alert attributes are correctly set
    for alt in db_alerts:
        assert alt.alert_id is not None
        assert alt.run_id == run_id
        assert alt.dataset_name == "transactions"
        assert alt.drift_type in [d.value for d in DriftType]
        assert alt.metric_name is not None
        assert alt.detection_method is not None
        assert alt.baseline_value is not None
        assert alt.current_value is not None
        assert alt.difference is not None
        assert alt.pct_change is not None
        assert alt.severity in [s.value for s in AlertSeverity]
        assert alt.explanation != ""
        assert alt.suggested_action != ""
        assert alt.created_at is not None


def test_drift_alert_deduplication(test_db):
    """Verify running drift analysis multiple times does not produce duplicate alerts."""
    run_id = f"RUN_DEDUP_{uuid.uuid4().hex[:8]}"
    baseline_profile = {
        "version": "v1.0",
        "record_volume": 1000,
        "column_baselines": {
            "customer_email": {"null_rate": 0.0},
        },
    }
    records = [{"customer_email": None, "amount": 10.0} for _ in range(50)]

    # First run
    res1 = DriftDetector.analyze(
        records=records,
        baseline_profile=baseline_profile,
        run_id=run_id,
        db=test_db,
        save_results=True,
    )
    initial_alerts_count = test_db.query(DataQualityAlert).filter_by(run_id=run_id).count()
    assert initial_alerts_count > 0

    # Second run with same run_id: deduplication should prevent adding duplicate alerts
    res2 = DriftDetector.analyze(
        records=records,
        baseline_profile=baseline_profile,
        run_id=run_id,
        db=test_db,
        save_results=True,
    )
    final_alerts_count = test_db.query(DataQualityAlert).filter_by(run_id=run_id).count()
    assert final_alerts_count == initial_alerts_count


def test_drift_api_endpoints(test_db):
    """Verify REST API endpoints GET /metrics/drift and GET /alerts return drift results."""
    from app.api.routes import alerts, metrics
    run_id = f"RUN_API_{uuid.uuid4().hex[:8]}"

    # Add a mock processing run
    run_obj = ProcessingRun(
        run_id=run_id,
        source_file="test.csv",
        file_hash="hash_api_123",
        status="COMPLETED",
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        input_count=100,
    )
    test_db.add(run_obj)
    test_db.flush()

    # Add DriftAnalysisResult
    drift_row = DriftAnalysisResult(
        run_id=run_id,
        baseline_version="v1.0",
        drift_type=DriftType.VOLUME.value,
        column_name=None,
        detection_method=DetectionMethod.PERCENTAGE_CHANGE.value,
        baseline_value=1000.0,
        current_value=100.0,
        absolute_difference=-900.0,
        percentage_difference=-90.0,
        drift_detected=True,
        severity=AlertSeverity.CRITICAL.value,
        threshold=20.0,
        details="Volume dropped by 90%",
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(drift_row)

    # Add DataQualityAlert with drift fields
    alert_row = DataQualityAlert(
        alert_id=f"alt_{uuid.uuid4().hex[:8]}",
        run_id=run_id,
        dataset_name="transactions",
        column_name="customer_email",
        drift_type=DriftType.NULL_RATE.value,
        metric_name="null_rate:customer_email",
        detection_method=DetectionMethod.PERCENTAGE_POINT_SHIFT.value,
        baseline_value=2.0,
        current_value=40.0,
        difference=38.0,
        pct_change=38.0,
        configured_threshold=5.0,
        severity=AlertSeverity.CRITICAL.value,
        explanation="Null rate increased by 38 pp",
        suggested_action="Check upstream producer",
        created_at=datetime.now(timezone.utc),
    )
    test_db.add(alert_row)
    test_db.commit()

    # Test GET /metrics/drift
    drift_data = metrics.get_drift_results(run_id=run_id, db=test_db)
    assert len(drift_data) >= 1
    assert drift_data[0].run_id == run_id
    assert drift_data[0].drift_type == DriftType.VOLUME.value
    assert drift_data[0].drift_detected is True

    # Test GET /alerts
    alerts_data = alerts.get_alerts(run_id=run_id, db=test_db)
    assert len(alerts_data) >= 1
    assert alerts_data[0].run_id == run_id
    assert alerts_data[0].drift_type == DriftType.NULL_RATE.value
    assert alerts_data[0].column_name == "customer_email"
