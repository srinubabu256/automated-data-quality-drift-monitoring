"""Tests for baseline comparisons and explainable alert generation."""
from app.models.database_models import BaselineProfile, DataQualityProfile, DataQualityAlert
from app.alerts.alert_engine import AlertEngine


def test_volume_drop_alert_generation(test_db):
    """Verify volume drop greater than threshold triggers explainable alert."""
    # Baseline: 10,000 records
    baseline = BaselineProfile(
        version="v1.0_alert_test",
        baseline_name="Test Baseline",
        record_volume=10000,
        null_rate=0.015,
        mean_amount=150.00,
        std_amount=45.00,
        min_amount=5.00,
        max_amount=1200.00,
        median_amount=140.00,
        p95_amount=230.00,
        event_freshness_sec=3600.0,
        is_active=True,
    )
    test_db.add(baseline)
    test_db.commit()

    # Current run: 3,000 records (-70% volume drop)
    profile = DataQualityProfile(
        run_id="run_alert_vol_drop",
        batch_volume=3000,
        null_rate=0.015,
        mean_amount=150.00,
        std_amount=45.00,
        min_amount=5.00,
        max_amount=1200.00,
        median_amount=140.00,
        p95_amount=230.00,
        event_freshness_sec=3600.0,
    )
    test_db.add(profile)
    test_db.commit()

    alerts = AlertEngine.evaluate_run(test_db, "run_alert_vol_drop", profile, baseline)
    assert len(alerts) >= 1

    vol_alert = next((a for a in alerts if a.metric_name == "record_volume"), None)
    assert vol_alert is not None
    assert vol_alert.severity in ["WARNING", "CRITICAL"]
    assert vol_alert.pct_change == -70.0
    assert "70.0%" in vol_alert.explanation
    assert vol_alert.suggested_action is not None


def test_null_rate_spike_alert(test_db):
    """Verify null rate increase generates explainable data quality alert."""
    baseline = BaselineProfile(
        version="v1.0_null_test",
        baseline_name="Test Baseline",
        record_volume=1000,
        null_rate=0.02,  # 2%
        mean_amount=100.00,
        std_amount=20.00,
        min_amount=10.00,
        max_amount=500.00,
        median_amount=100.00,
        p95_amount=200.00,
        event_freshness_sec=3600.0,
        is_active=True,
    )
    test_db.add(baseline)
    test_db.commit()

    # Current profile: 25% null rate (increase of 23 percentage points)
    profile = DataQualityProfile(
        run_id="run_null_spike",
        batch_volume=1000,
        null_rate=0.25,
        mean_amount=100.00,
        std_amount=20.00,
        min_amount=10.00,
        max_amount=500.00,
        median_amount=100.00,
        p95_amount=200.00,
        event_freshness_sec=3600.0,
    )
    test_db.add(profile)
    test_db.commit()

    alerts = AlertEngine.evaluate_run(test_db, "run_null_spike", profile, baseline)
    null_alert = next((a for a in alerts if a.metric_name == "null_rate"), None)
    assert null_alert is not None
    assert null_alert.pct_change == 23.0  # 23 percentage points
    assert "23.0 percentage points" in null_alert.explanation


def test_prevent_duplicate_alerts_for_same_run(test_db):
    """Verify evaluating the same profile twice does not insert duplicate alerts."""
    baseline = BaselineProfile(
        version="v1.0_dup_alert",
        baseline_name="Test Baseline",
        record_volume=1000,
        null_rate=0.01,
        mean_amount=100.00,
        std_amount=20.00,
        min_amount=10.00,
        max_amount=500.00,
        median_amount=100.00,
        p95_amount=200.00,
        event_freshness_sec=3600.0,
        is_active=True,
    )
    test_db.add(baseline)

    profile = DataQualityProfile(
        run_id="run_dup_eval",
        batch_volume=200,  # 80% drop
        null_rate=0.01,
        mean_amount=100.00,
        std_amount=20.00,
        min_amount=10.00,
        max_amount=500.00,
        median_amount=100.00,
        p95_amount=200.00,
        event_freshness_sec=3600.0,
    )
    test_db.add(profile)
    test_db.commit()

    # First evaluation
    AlertEngine.evaluate_run(test_db, "run_dup_eval", profile, baseline)
    count_1 = test_db.query(DataQualityAlert).filter_by(run_id="run_dup_eval").count()

    # Second evaluation
    AlertEngine.evaluate_run(test_db, "run_dup_eval", profile, baseline)
    count_2 = test_db.query(DataQualityAlert).filter_by(run_id="run_dup_eval").count()

    assert count_1 == count_2
