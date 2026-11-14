"""Tests for ReportGenerator and Reconciliation audit exports."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.database_models import (
    Base,
    ProcessingRun,
    DailyMetric,
    DataQualityProfile,
    DataQualityAlert,
    RejectedRecord,
    BaselineProfile,
)
from app.reporting.report_generator import ReportGenerator, sanitize_csv_cell, sanitize_dict_for_csv


@pytest.fixture
def report_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_sanitize_csv_cell_formula_injection():
    """Verify spreadsheet formula injection characters (CWE-1236) are prepended with single-quote."""
    dangerous_inputs = [
        "=SUM(A1:B10)",
        "+1+2",
        "-5*2",
        "@SUM(1,2)",
        "\tmalicious_tab",
        "\rmalicious_cr",
    ]
    for val in dangerous_inputs:
        sanitized = sanitize_csv_cell(val)
        assert sanitized.startswith("'"), f"Failed for {val}"

    # Safe strings and non-string types must remain unchanged
    safe_inputs = ["NORMAL_TXN_001", "CUST_999", 123, 45.67, None, True]
    for val in safe_inputs:
        assert sanitize_csv_cell(val) == val


def test_sanitize_dict_for_csv():
    """Verify entire dictionary is sanitized before CSV writing."""
    row = {
        "id": "TXN_1",
        "formula": "=1+1",
        "amount": 100.5,
        "clean_text": "hello"
    }
    cleaned = sanitize_dict_for_csv(row)
    assert cleaned["formula"] == "'=1+1"
    assert cleaned["id"] == "TXN_1"
    assert cleaned["amount"] == 100.5


def test_generate_all_reports_empty_db(report_db, tmp_path):
    """Verify report generation runs gracefully on an empty database."""
    generator = ReportGenerator(output_dir=tmp_path)
    reports = generator.generate_all_reports(report_db)

    assert "runs" in reports
    assert "daily_metrics" in reports
    assert "data_quality" in reports
    assert "alerts" in reports
    assert "baseline_comparison" in reports

    # Check that output JSON files exist and are valid JSON
    for key, file_path in reports.items():
        if file_path:  # reconciliation might be empty string when no runs exist
            p = Path(file_path)
            assert p.exists()
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert isinstance(data, (list, dict))


def test_generate_all_reports_with_data(report_db, tmp_path):
    """Verify comprehensive report generation with populated run and quality data."""
    now = datetime.now(timezone.utc)
    run_id = "run_report_test_01"

    # Add run
    run = ProcessingRun(
        run_id=run_id,
        source_file="test_export.csv",
        file_hash="hash_export_123",
        status="SUCCESS",
        input_count=100,
        accepted_count=90,
        rejected_count=8,
        duplicate_count=2,
        processed_count=90,
        start_time=now,
        end_time=now,
        execution_duration_sec=1.5,
    )
    report_db.add(run)

    # Add baseline
    baseline = BaselineProfile(
        version="v1.0",
        baseline_name="Baseline v1.0",
        is_active=True,
        record_volume=100,
        null_rate=0.05,
        mean_amount=150.0,
        std_amount=30.0,
        min_amount=10.0,
        max_amount=500.0,
        event_freshness_sec=3600.0,
    )
    report_db.add(baseline)

    # Add profile
    profile = DataQualityProfile(
        run_id=run_id,
        batch_volume=100,
        null_rate=0.08,
        mean_amount=160.0,
        std_amount=32.0,
        min_amount=12.0,
        max_amount=480.0,
        median_amount=155.0,
        p95_amount=350.0,
        event_freshness_sec=3600.0,
    )
    report_db.add(profile)

    # Add alert
    alert = DataQualityAlert(
        alert_id="alert_rep_01",
        run_id=run_id,
        metric_name="null_rate",
        baseline_value=0.05,
        current_value=0.08,
        difference=0.03,
        pct_change=3.0,
        severity="WARNING",
        explanation="Null rate increased by 3.0 percentage points.",
        suggested_action="Check quarantined records.",
        is_resolved=False,
    )
    report_db.add(alert)

    # Add rejected record
    rej = RejectedRecord(
        run_id=run_id,
        source_file="test_export.csv",
        line_number=42,
        raw_data="corrupt,row,here",
        rejection_code="INVALID_AMOUNT_VALUE",
        rejection_reason="Amount is negative",
        rejected_at=now,
    )
    report_db.add(rej)

    report_db.commit()

    # Generate all reports
    generator = ReportGenerator(output_dir=tmp_path)
    reports = generator.generate_all_reports(report_db, run_id=run_id)

    assert Path(reports["reconciliation"]).exists()
    assert Path(reports["runs"]).exists()
    assert Path(reports["data_quality"]).exists()
    assert Path(reports["alerts"]).exists()
    assert Path(reports["rejected_records"]).exists()
    assert Path(reports["baseline_comparison"]).exists()

    # Verify reconciliation math balance
    with open(reports["reconciliation"], "r", encoding="utf-8") as f:
        recon = json.load(f)
        assert recon["status"] == "BALANCED"
        assert recon["reconciled"] is True
        assert recon["counts"]["input_count"] == 100
        assert recon["counts"]["accepted_count"] == 90
        assert recon["counts"]["rejected_count"] == 8
        assert recon["counts"]["duplicate_count"] == 2
        assert recon["counts"]["discrepancy"] == 0
