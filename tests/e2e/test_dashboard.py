"""Tests for the interactive observability dashboard."""
from datetime import datetime, timezone
import pytest
from app.main import app
from dashboard.app import dashboard_app, get_dashboard_html
from app.database.models import ProcessingRun, DataQualityAlert, DriftAnalysisResult, DailyMetric


def test_dashboard_direct_route_render(test_db):
    """Verify get_dashboard_html returns valid HTML response containing tabs and metrics."""
    resp = get_dashboard_html(db=test_db)
    assert resp.status_code == 200
    html_content = resp.body.decode("utf-8")
    assert "YottaFlex" in html_content
    assert "Drift Radar" in html_content
    assert "Anomaly Alerts" in html_content
    assert "Ingestion Batches" in html_content
    assert "Daily Business Metrics" in html_content


def test_dashboard_mounted_in_main_app():
    """Verify dashboard sub-application is mounted at /dashboard on main FastAPI app."""
    mounted_paths = [route.path for route in app.routes]
    assert any("/dashboard" in p for p in mounted_paths)
    assert dashboard_app.title == "YottaFlex Platform Dashboard"


def test_dashboard_renders_with_seeded_data(test_db):
    """Verify dashboard dynamically populates tables when data exists in database."""
    # Seed a run
    run = ProcessingRun(
        run_id="run_e2e_dashboard_001",
        source_file="test_feed.csv",
        file_hash="abc123hash",
        status="COMPLETED",
        input_count=500,
        accepted_count=490,
        rejected_count=10,
        duplicate_count=0,
        execution_duration_sec=1.25,
    )
    # Seed an alert
    alert = DataQualityAlert(
        alert_id="ALT_TEST_001",
        run_id="run_e2e_dashboard_001",
        metric_name="record_volume",
        baseline_value=10000.0,
        current_value=500.0,
        difference=-9500.0,
        pct_change=-95.0,
        severity="CRITICAL",
        explanation="Batch volume dropped by 45.0%",
        suggested_action="Check upstream publisher",
    )
    # Seed drift result
    drift = DriftAnalysisResult(
        run_id="run_e2e_dashboard_001",
        baseline_version="v1.0",
        drift_type="VOLUME",
        column_name=None,
        detection_method="Percentage Difference",
        baseline_value=10000.0,
        current_value=500.0,
        absolute_difference=-9500.0,
        percentage_difference=-95.0,
        drift_detected=True,
        severity="CRITICAL",
        details="Volume drop exceeds critical threshold",
    )
    # Seed daily metric
    metric = DailyMetric(
        metric_date=datetime.now(timezone.utc).date(),
        dimension_type="GLOBAL",
        dimension_value="ALL",
        total_transactions=490,
        total_amount=49000.0,
        avg_amount=100.0,
        active_customers=120,
        active_products=35,
        null_rate=0.002,
    )
    test_db.add_all([run, alert, drift, metric])
    test_db.commit()

    resp = get_dashboard_html(db=test_db)
    assert resp.status_code == 200
    html = resp.body.decode("utf-8")
    assert "run_e2e_dashboard_001" in html
    assert "ALT_TEST_001" in html
    assert "VOLUME" in html
    assert "-95.00%" in html
    assert "490" in html


def test_streamlit_dashboard_syntax_and_structure():
    """Verify Streamlit dashboard file exists, compiles cleanly, and includes all required views."""
    import py_compile
    from pathlib import Path
    st_path = Path("dashboard/streamlit_app.py")
    assert st_path.exists(), "dashboard/streamlit_app.py must exist"

    # Verify python compilation
    compiled = py_compile.compile(str(st_path), doraise=True)
    assert compiled is not None

    content = st_path.read_text(encoding="utf-8")
    required_views = [
        "Overview",
        "Data Upload",
        "Data Profiling",
        "Baseline Management",
        "Drift Monitoring",
        "Alert Center",
        "Batch Monitoring",
        "Reconciliation",
    ]
    for view in required_views:
        assert view in content, f"Missing required view: {view}"
