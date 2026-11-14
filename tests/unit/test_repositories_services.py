"""Unit tests for repositories and services layer."""
from datetime import datetime, timezone, date
import pytest

from app.database.models import ProcessingRun, RejectedRecord, DailyMetric, DataQualityProfile, DataQualityAlert, DriftAnalysisResult, BaselineProfile
from app.database.repositories.batch_repository import BatchRepository
from app.database.repositories.metric_repository import MetricRepository
from app.database.repositories.alert_repository import AlertRepository
from app.database.repositories.baseline_repository import BaselineRepository
from app.services.batch_service import BatchService
from app.services.baseline_service import BaselineService
from app.services.drift_service import DriftService
from app.services.report_service import ReportService


def test_repositories_crud(test_db):
    """Verify repository methods query and filter models correctly."""
    # Seed run
    run = ProcessingRun(
        run_id="run_repo_test_01",
        source_file="test_feed.csv",
        file_hash="hash_repo_01",
        status="COMPLETED",
        input_count=100,
        accepted_count=98,
        rejected_count=2,
    )
    rej = RejectedRecord(
        run_id="run_repo_test_01",
        source_file="test_feed.csv",
        line_number=5,
        raw_data="{}",
        rejection_reason="Negative amount",
        rejection_code="INVALID_AMOUNT",
    )
    metric = DailyMetric(
        metric_date=date(2026, 11, 12),
        dimension_type="GLOBAL",
        dimension_value="ALL",
        total_transactions=98,
        total_amount=9800.0,
        avg_amount=100.0,
    )
    profile = DataQualityProfile(
        run_id="run_repo_test_01",
        batch_volume=100,
        null_rate=0.01,
        mean_amount=100.0,
    )
    alert = DataQualityAlert(
        alert_id="ALT_REPO_01",
        run_id="run_repo_test_01",
        metric_name="record_volume",
        baseline_value=1000.0,
        current_value=100.0,
        difference=-900.0,
        pct_change=-90.0,
        severity="WARNING",
        explanation="Volume down",
        suggested_action="Review",
    )
    drift = DriftAnalysisResult(
        run_id="run_repo_test_01",
        baseline_version="v1.0",
        drift_type="VOLUME",
        detection_method="Percentage Difference",
        drift_detected=True,
        severity="WARNING",
    )
    test_db.add_all([run, rej, metric, profile, alert, drift])
    test_db.commit()

    # BatchRepository
    assert BatchRepository.get_run(test_db, "run_repo_test_01") is not None
    assert BatchRepository.get_run_by_hash(test_db, "hash_repo_01") is not None
    assert len(BatchRepository.list_runs(test_db, status="COMPLETED")) >= 1
    assert len(BatchRepository.get_rejected_records(test_db, run_id="run_repo_test_01")) == 1

    # MetricRepository
    assert len(MetricRepository.get_daily_metrics(test_db, dimension="GLOBAL")) >= 1
    assert len(MetricRepository.get_quality_profiles(test_db, run_id="run_repo_test_01")) == 1

    # AlertRepository
    assert len(AlertRepository.get_alerts(test_db, run_id="run_repo_test_01", severity="WARNING")) == 1
    assert len(AlertRepository.get_drift_results(test_db, run_id="run_repo_test_01", drift_detected=True)) == 1

    # BaselineRepository
    active_baseline = BaselineRepository.get_active(test_db, version="v1.0")
    assert active_baseline is not None
    assert len(BaselineRepository.list_all(test_db)) >= 1


def test_services_layer(test_db):
    """Verify service layer facade delegations."""
    # BatchService
    runs = BatchService.list_runs(test_db)
    assert isinstance(runs, list)

    # BaselineService
    b = BaselineService.get_active(test_db)
    assert b is not None
    all_b = BaselineService.list_baselines(test_db)
    assert len(all_b) >= 1

    # DriftService
    drift_res = DriftService.query_drift_results(test_db)
    assert isinstance(drift_res, list)

    # ReportService
    alerts = ReportService.get_alerts(test_db)
    assert isinstance(alerts, list)
