"""YottaFlex Data Quality & Drift Monitoring Platform Dashboard.

Provides an interactive real-time visual web application for pipeline monitoring,
multi-dimensional drift radar, explainable anomaly alerts, and reconciliation audit.

Usage:
    python dashboard/app.py
    # or start with uvicorn dashboard.app:dashboard_app --port 8501
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import uvicorn

from app.database import get_db
from app.database.models import ProcessingRun, DailyMetric, DataQualityAlert, DriftAnalysisResult

dashboard_app = FastAPI(
    title="YottaFlex Platform Dashboard",
    description="Operational observability and drift monitoring dashboard",
    version="1.0.0",
)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YottaFlex Data Quality & Drift Platform</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .navbar-brand { font-weight: 700; letter-spacing: -0.5px; }
        .card { border: none; border-radius: 10px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); }
        .stat-card { transition: transform 0.2s; }
        .stat-card:hover { transform: translateY(-3px); }
        .stat-num { font-size: 2rem; font-weight: 700; }
        .badge-critical { background-color: #dc3545; }
        .badge-warning { background-color: #ffc107; color: #000; }
        .badge-completed { background-color: #198754; }
        .nav-pills .nav-link.active { background-color: #0d6efd; }
        .table-responsive { max-height: 480px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark px-4 py-3 shadow-sm">
        <a class="navbar-brand text-primary" href="#">YottaFlex <span class="text-white">Observability & Drift Platform</span></a>
        <span class="badge bg-success ms-auto">System Operational (SQLite Engine)</span>
    </nav>

    <div class="container-fluid py-4 px-4">
        <!-- Top Stats Row -->
        <div class="row g-3 mb-4">
            <div class="col-md-3">
                <div class="card stat-card p-3 bg-white">
                    <div class="text-muted small text-uppercase fw-bold">Total Ingestion Runs</div>
                    <div class="stat-num text-primary">{total_runs}</div>
                    <div class="small text-muted">{completed_runs} Completed successfully</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stat-card p-3 bg-white">
                    <div class="text-muted small text-uppercase fw-bold">Total Transactions</div>
                    <div class="stat-num text-success">{total_transactions:,}</div>
                    <div class="small text-muted">{rejected_transactions:,} Quarantined / Rejected</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stat-card p-3 bg-white">
                    <div class="text-muted small text-uppercase fw-bold">Active Quality Alerts</div>
                    <div class="stat-num text-danger">{total_alerts}</div>
                    <div class="small text-muted">{critical_alerts} Critical Severity</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stat-card p-3 bg-white">
                    <div class="text-muted small text-uppercase fw-bold">Drift Tests Executed</div>
                    <div class="stat-num text-info">{drift_tests_count}</div>
                    <div class="small text-muted">{drift_detected_count} Drift Anomalies Detected</div>
                </div>
            </div>
        </div>

        <!-- Navigation Tabs -->
        <ul class="nav nav-pills mb-4" id="pills-tab" role="tablist">
            <li class="nav-item"><button class="nav-link active" data-bs-toggle="pill" data-bs-target="#tab-drift">Drift Radar</button></li>
            <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-alerts">Anomaly Alerts</button></li>
            <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-runs">Ingestion Batches</button></li>
            <li class="nav-item"><button class="nav-link" data-bs-toggle="pill" data-bs-target="#tab-metrics">Daily Business Metrics</button></li>
        </ul>

        <div class="tab-content" id="pills-tabContent">
            <!-- Drift Radar Tab -->
            <div class="tab-pane fade show active" id="tab-drift">
                <div class="card p-4">
                    <h5 class="fw-bold mb-3">Multi-Dimensional Drift Findings</h5>
                    <p class="text-muted small">Tracks volume spikes/drops, column null-rate shifts, continuous distribution PSI & KS tests, and categorical Chi-Square tests.</p>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-light">
                                <tr>
                                    <th>Run ID</th>
                                    <th>Drift Type</th>
                                    <th>Column</th>
                                    <th>Method</th>
                                    <th>Baseline</th>
                                    <th>Current</th>
                                    <th>Shift / Diff</th>
                                    <th>Stat / p-value</th>
                                    <th>Drift Detected</th>
                                    <th>Severity</th>
                                </tr>
                            </thead>
                            <tbody>
                                {drift_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Alerts Tab -->
            <div class="tab-pane fade" id="tab-alerts">
                <div class="card p-4">
                    <h5 class="fw-bold mb-3">Explainable Anomaly Alerts Feed</h5>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-light">
                                <tr>
                                    <th>Alert ID</th>
                                    <th>Run ID</th>
                                    <th>Metric</th>
                                    <th>Severity</th>
                                    <th>Explanation</th>
                                    <th>Recommended Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {alert_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Runs Tab -->
            <div class="tab-pane fade" id="tab-runs">
                <div class="card p-4">
                    <h5 class="fw-bold mb-3">Batch Ingestion History</h5>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-light">
                                <tr>
                                    <th>Run ID</th>
                                    <th>Source File</th>
                                    <th>Status</th>
                                    <th>Input Rows</th>
                                    <th>Accepted</th>
                                    <th>Rejected</th>
                                    <th>Duplicates</th>
                                    <th>Duration (s)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {run_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Metrics Tab -->
            <div class="tab-pane fade" id="tab-metrics">
                <div class="card p-4">
                    <h5 class="fw-bold mb-3">Daily Business Metrics</h5>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-light">
                                <tr>
                                    <th>Date</th>
                                    <th>Dimension</th>
                                    <th>Transactions</th>
                                    <th>Total Amount</th>
                                    <th>Avg Amount</th>
                                    <th>Active Cust</th>
                                    <th>Active Prod</th>
                                    <th>Null Rate</th>
                                </tr>
                            </thead>
                            <tbody>
                                {metric_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""


@dashboard_app.get("/", response_class=HTMLResponse)
@dashboard_app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard_html(db: Session = Depends(get_db)):
    """Renders the comprehensive YottaFlex observability dashboard."""
    runs = db.query(ProcessingRun).order_by(ProcessingRun.start_time.desc()).limit(20).all()
    alerts = db.query(DataQualityAlert).order_by(DataQualityAlert.created_at.desc()).limit(20).all()
    drifts = db.query(DriftAnalysisResult).order_by(DriftAnalysisResult.id.desc()).limit(20).all()
    metrics = db.query(DailyMetric).order_by(DailyMetric.metric_date.desc()).limit(20).all()

    total_runs = db.query(ProcessingRun).count()
    completed_runs = db.query(ProcessingRun).filter_by(status="COMPLETED").count()
    total_tx = sum(r.input_count for r in runs)
    rej_tx = sum(r.rejected_count for r in runs)
    total_alerts = len(alerts)
    crit_alerts = sum(1 for a in alerts if str(a.severity).upper() == "CRITICAL")
    drift_count = len(drifts)
    drift_detected_count = sum(1 for d in drifts if d.drift_detected)

    # Format Drift Rows
    drift_rows = ""
    for d in drifts:
        badge_cls = "bg-danger" if d.drift_detected else "bg-success"
        stat_p = ""
        if d.statistical_statistic is not None:
            stat_p += f"Stat: {d.statistical_statistic:.3f}"
        if d.p_value is not None:
            stat_p += f" (p={d.p_value:.3f})"
        diff_str = f"{d.percentage_difference:+.2f}%" if d.percentage_difference is not None else "-"
        drift_rows += f"""
        <tr>
            <td><code>{d.run_id[:16]}</code></td>
            <td><span class="badge bg-secondary">{d.drift_type}</span></td>
            <td><code>{d.column_name or 'TABLE'}</code></td>
            <td><small>{d.detection_method}</small></td>
            <td>{d.baseline_value or '-'}</td>
            <td>{d.current_value or '-'}</td>
            <td><strong>{diff_str}</strong></td>
            <td><small>{stat_p or '-'}</small></td>
            <td><span class="badge {badge_cls}">{'DRIFT' if d.drift_detected else 'STABLE'}</span></td>
            <td><span class="badge bg-warning text-dark">{d.severity}</span></td>
        </tr>
        """

    # Format Alert Rows
    alert_rows = ""
    for a in alerts:
        sev_bg = "bg-danger" if a.severity == "CRITICAL" else "bg-warning text-dark"
        alert_rows += f"""
        <tr>
            <td><code>{a.alert_id}</code></td>
            <td><code>{a.run_id[:16]}</code></td>
            <td><strong>{a.metric_name}</strong></td>
            <td><span class="badge {sev_bg}">{a.severity}</span></td>
            <td><small>{a.explanation}</small></td>
            <td><small class="text-primary">{a.suggested_action}</small></td>
        </tr>
        """

    # Format Run Rows
    run_rows = ""
    for r in runs:
        status_bg = "badge-completed" if r.status == "COMPLETED" else "badge-warning"
        run_rows += f"""
        <tr>
            <td><code>{r.run_id}</code></td>
            <td>{r.source_file}</td>
            <td><span class="badge {status_bg}">{r.status}</span></td>
            <td>{r.input_count:,}</td>
            <td>{r.accepted_count:,}</td>
            <td>{r.rejected_count:,}</td>
            <td>{r.duplicate_count:,}</td>
            <td>{r.execution_duration_sec:.2f}</td>
        </tr>
        """

    # Format Metric Rows
    metric_rows = ""
    for m in metrics:
        metric_rows += f"""
        <tr>
            <td>{m.metric_date}</td>
            <td><span class="badge bg-info text-dark">{m.dimension_type} ({m.dimension_value})</span></td>
            <td>{m.total_transactions:,}</td>
            <td>${float(m.total_amount):,.2f}</td>
            <td>${float(m.avg_amount):,.2f}</td>
            <td>{m.active_customers:,}</td>
            <td>{m.active_products:,}</td>
            <td>{m.null_rate * 100:.2f}%</td>
        </tr>
        """

    html = HTML_TEMPLATE
    replacements = {
        "{total_runs}": str(total_runs),
        "{completed_runs}": str(completed_runs),
        "{total_transactions}": f"{total_tx:,}",
        "{rejected_transactions}": f"{rej_tx:,}",
        "{total_alerts}": str(total_alerts),
        "{critical_alerts}": str(crit_alerts),
        "{drift_tests_count}": str(drift_count),
        "{drift_detected_count}": str(drift_detected_count),
        "{drift_rows}": drift_rows or '<tr><td colspan="10" class="text-center text-muted">No drift results recorded yet.</td></tr>',
        "{alert_rows}": alert_rows or '<tr><td colspan="6" class="text-center text-muted">No quality alerts recorded.</td></tr>',
        "{run_rows}": run_rows or '<tr><td colspan="8" class="text-center text-muted">No ingestion runs found.</td></tr>',
        "{metric_rows}": metric_rows or '<tr><td colspan="8" class="text-center text-muted">No daily metrics computed.</td></tr>',
    }
    for placeholder, val in replacements.items():
        html = html.replace(placeholder, val)
    return HTMLResponse(content=html)


if __name__ == "__main__":
    port = int(os.environ.get("DASHBOARD_PORT", 8501))
    print(f"Starting YottaFlex Platform Dashboard on http://127.0.0.1:{port}...")
    uvicorn.run("dashboard.app:dashboard_app", host="127.0.0.1", port=port, reload=False)
