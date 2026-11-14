"""Extended tests for explainable anomaly alert evaluation."""
import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts.alert_engine import AlertEngine
from app.config import settings
from app.models.database_models import Base, BaselineProfile, DataQualityProfile, ProcessingRun


@pytest.fixture
def alert_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def create_mock_run(db, run_id):
    run = ProcessingRun(
        run_id=run_id,
        source_file="test_batch.csv",
        file_hash="hash_mock_alert",
        status="SUCCESS",
        input_count=1000,
        accepted_count=1000,
        rejected_count=0,
        duplicate_count=0,
        processed_count=1000,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    return run


def test_volume_spike_alert(alert_db):
    """Verify volume spike generates an explainable alert."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    create_mock_run(alert_db, run_id)

    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Baseline v1.0",
        is_active=True,
        record_volume=10000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        event_freshness_sec=3600.0,
    )
    alert_db.add(baseline)
    alert_db.commit()

    # Profile with 20000 records (+100% surge > 50% threshold)
    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=20000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        min_amount=10.0,
        max_amount=200.0,
        event_freshness_sec=3600.0,
    )
    alert_db.add(profile)
    alert_db.commit()

    alerts = AlertEngine.evaluate_batch(alert_db, profile, baseline)
    spike_alerts = [a for a in alerts if a.metric_name == "record_volume_spike"]
    assert len(spike_alerts) == 1
    assert "surged by 100.0%" in spike_alerts[0].explanation
    assert spike_alerts[0].severity == "WARNING"


def test_freshness_violation_alert(alert_db):
    """Verify event freshness latency alert is generated when threshold exceeded."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    create_mock_run(alert_db, run_id)

    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Baseline v1.0",
        is_active=True,
        record_volume=10000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        event_freshness_sec=3600.0,
    )

    # Latency: 100,000 seconds (> 86,400s threshold)
    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=10000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        min_amount=10.0,
        max_amount=200.0,
        event_freshness_sec=100000.0,
    )
    alert_db.add(profile)
    alert_db.commit()

    alerts = AlertEngine.evaluate_batch(alert_db, profile, baseline)
    freshness_alerts = [a for a in alerts if a.metric_name == "event_freshness"]
    assert len(freshness_alerts) == 1
    assert "exceeds maximum allowable latency" in freshness_alerts[0].explanation


def test_amount_drift_alert(alert_db):
    """Verify mean transaction amount drift generates warning alert."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    create_mock_run(alert_db, run_id)

    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Baseline v1.0",
        is_active=True,
        record_volume=10000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        event_freshness_sec=3600.0,
    )

    # Mean amount $200 vs $100 baseline (+100% drift > 25% threshold)
    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=10000,
        null_rate=0.01,
        mean_amount=200.0,
        std_amount=20.0,
        min_amount=10.0,
        max_amount=500.0,
        event_freshness_sec=3600.0,
    )
    alert_db.add(profile)
    alert_db.commit()

    alerts = AlertEngine.evaluate_batch(alert_db, profile, baseline)
    amount_alerts = [a for a in alerts if a.metric_name == "mean_amount"]
    assert len(amount_alerts) == 1
    assert "higher than baseline" in amount_alerts[0].explanation


def test_null_rate_spike_alert(alert_db):
    """Verify null/rejection rate spike generates warning or critical alert."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    create_mock_run(alert_db, run_id)

    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Baseline v1.0",
        is_active=True,
        record_volume=10000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        event_freshness_sec=3600.0,
    )

    # Null rate 0.25 (25% vs 1% baseline -> 24 percentage points increase -> CRITICAL)
    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=10000,
        null_rate=0.25,
        mean_amount=100.0,
        std_amount=20.0,
        min_amount=10.0,
        max_amount=200.0,
        event_freshness_sec=3600.0,
    )
    alert_db.add(profile)
    alert_db.commit()

    alerts = AlertEngine.evaluate_batch(alert_db, profile, baseline)
    null_alerts = [a for a in alerts if a.metric_name == "null_rate"]
    assert len(null_alerts) == 1
    assert null_alerts[0].severity == "CRITICAL"
    assert "24.0 percentage points" in null_alerts[0].explanation


def test_zero_baseline_division_safety(alert_db):
    """Verify zero baseline volume or mean does not trigger ZeroDivisionError."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    create_mock_run(alert_db, run_id)

    zero_baseline = BaselineProfile(
        version="zero_v1",
        baseline_name="Zero Base",
        is_active=True,
        record_volume=0,
        null_rate=0.0,
        mean_amount=0.0,
        std_amount=0.0,
        event_freshness_sec=0.0,
    )

    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=1000,
        null_rate=0.0,
        mean_amount=100.0,
        std_amount=10.0,
        min_amount=10.0,
        max_amount=200.0,
        event_freshness_sec=3600.0,
    )

    # Must complete safely without ZeroDivisionError
    alerts = AlertEngine.evaluate_batch(alert_db, profile, zero_baseline)
    assert isinstance(alerts, list)


def test_missing_baseline_graceful_exit(alert_db):
    """Verify evaluate_batch returns empty list gracefully when no baseline exists."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    create_mock_run(alert_db, run_id)

    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=1000,
        null_rate=0.0,
        mean_amount=100.0,
        std_amount=10.0,
        min_amount=10.0,
        max_amount=200.0,
        event_freshness_sec=3600.0,
    )

    alerts = AlertEngine.evaluate_batch(alert_db, profile, baseline=None)
    assert alerts == []


def test_alert_generation_idempotency(alert_db):
    """Verify repeatedly evaluating the same run does not create duplicate alert rows."""
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    create_mock_run(alert_db, run_id)

    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Baseline v1.0",
        is_active=True,
        record_volume=10000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        event_freshness_sec=3600.0,
    )

    # 3000 records -> volume drop
    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=3000,
        null_rate=0.01,
        mean_amount=100.0,
        std_amount=20.0,
        min_amount=10.0,
        max_amount=200.0,
        event_freshness_sec=3600.0,
    )
    alert_db.add(profile)
    alert_db.commit()

    first_eval = AlertEngine.evaluate_batch(alert_db, profile, baseline)
    assert len(first_eval) >= 1

    # Second evaluation of the same run and profile
    second_eval = AlertEngine.evaluate_batch(alert_db, profile, baseline)
    assert len(second_eval) == len(first_eval)

    # Total alert rows in database for this run must remain unchanged
    from app.models.database_models import DataQualityAlert
    total_alerts = alert_db.query(DataQualityAlert).filter_by(run_id=run_id).count()
    assert total_alerts == len(first_eval)
