"""Report Generator module creating machine-readable (JSON/CSV) and human-readable audit artifacts."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database_models import (
    ProcessingRun,
    DailyMetric,
    DataQualityProfile,
    DataQualityAlert,
    RejectedRecord,
    BaselineProfile,
)
from app.reporting.reconciliation import ReconciliationEngine


def sanitize_csv_cell(val: Any) -> Any:
    """Neutralize spreadsheet formula injection (CWE-1236) by escaping leading formula characters."""
    if isinstance(val, str) and val and val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{val}"
    return val


def sanitize_dict_for_csv(row: Dict[str, Any]) -> Dict[str, Any]:
    """Apply formula injection defense across all dictionary values."""
    return {k: sanitize_csv_cell(v) for k, v in row.items()}


class ReportGenerator:
    """Produces JSON and CSV report artifacts for audits, runs, metrics, and quality."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(settings.REPORTS_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all_reports(self, db: Session, run_id: Optional[str] = None) -> Dict[str, str]:
        """Generate all standard reports and save to disk."""
        generated_files = {}

        generated_files["reconciliation"] = self.generate_reconciliation_report(db, run_id)
        generated_files["runs"] = self.generate_run_report(db)
        generated_files["daily_metrics"] = self.generate_daily_metrics_report(db)
        generated_files["data_quality"] = self.generate_data_quality_report(db)
        generated_files["alerts"] = self.generate_alerts_report(db)
        generated_files["rejected_records"] = self.generate_rejected_records_report(db, run_id)
        generated_files["baseline_comparison"] = self.generate_baseline_comparison_report(db, run_id)

        return generated_files

    def generate_reconciliation_report(self, db: Session, run_id: Optional[str] = None) -> str:
        """Generate reconciliation report for specified run or latest run."""
        if not run_id:
            latest_run = db.query(ProcessingRun).order_by(ProcessingRun.start_time.desc()).first()
            if not latest_run:
                return ""
            run_id = latest_run.run_id

        reconciliation_data = ReconciliationEngine.reconcile_run(db, run_id)
        out_file = self.output_dir / f"reconciliation_report_{run_id}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(reconciliation_data, f, indent=2, default=str)
        return str(out_file)

    def generate_run_report(self, db: Session) -> str:
        """Export all processing runs to CSV and JSON."""
        runs = db.query(ProcessingRun).order_by(ProcessingRun.start_time.desc()).all()
        rows = []
        for r in runs:
            rows.append({
                "run_id": r.run_id,
                "source_file": r.source_file,
                "status": r.status,
                "input_count": r.input_count,
                "accepted_count": r.accepted_count,
                "rejected_count": r.rejected_count,
                "duplicate_count": r.duplicate_count,
                "processed_count": r.processed_count,
                "start_time": r.start_time.isoformat() if r.start_time else "",
                "end_time": r.end_time.isoformat() if r.end_time else "",
                "duration_sec": r.execution_duration_sec,
                "failure_reason": r.failure_reason or "",
            })

        out_json = self.output_dir / "processing_runs_report.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)

        out_csv = self.output_dir / "processing_runs_report.csv"
        if rows:
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows([sanitize_dict_for_csv(r) for r in rows])

        return str(out_json)

    def generate_daily_metrics_report(self, db: Session) -> str:
        """Export daily business metrics to CSV and JSON."""
        metrics = db.query(DailyMetric).order_by(DailyMetric.metric_date.desc()).all()
        rows = []
        for m in metrics:
            rows.append({
                "metric_date": str(m.metric_date),
                "dimension_type": m.dimension_type,
                "dimension_value": m.dimension_value,
                "total_transactions": m.total_transactions,
                "total_amount": float(m.total_amount),
                "active_customers": m.active_customers,
                "active_products": m.active_products,
                "avg_amount": float(m.avg_amount),
                "min_amount": float(m.min_amount),
                "max_amount": float(m.max_amount),
                "null_rate": m.null_rate,
                "record_volume": m.record_volume,
                "rejected_count": m.rejected_count,
                "duplicate_count": m.duplicate_count,
                "event_freshness_sec": m.event_freshness_sec,
                "computed_at": m.computed_at.isoformat() if m.computed_at else "",
            })

        out_json = self.output_dir / "daily_metrics_report.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)

        out_csv = self.output_dir / "daily_metrics_report.csv"
        if rows:
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows([sanitize_dict_for_csv(r) for r in rows])

        return str(out_json)

    def generate_data_quality_report(self, db: Session) -> str:
        """Export batch quality profiles to JSON."""
        profiles = db.query(DataQualityProfile).order_by(DataQualityProfile.created_at.desc()).all()
        rows = []
        for p in profiles:
            rows.append({
                "run_id": p.run_id,
                "batch_volume": p.batch_volume,
                "null_rate": p.null_rate,
                "mean_amount": p.mean_amount,
                "std_amount": p.std_amount,
                "min_amount": p.min_amount,
                "max_amount": p.max_amount,
                "median_amount": p.median_amount,
                "p95_amount": p.p95_amount,
                "event_freshness_sec": p.event_freshness_sec,
                "created_at": p.created_at.isoformat() if p.created_at else "",
            })

        out_json = self.output_dir / "data_quality_profiles_report.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        return str(out_json)

    def generate_alerts_report(self, db: Session) -> str:
        """Export alerts to CSV and JSON."""
        alerts = db.query(DataQualityAlert).order_by(DataQualityAlert.created_at.desc()).all()
        rows = []
        for a in alerts:
            rows.append({
                "alert_id": a.alert_id,
                "run_id": a.run_id,
                "metric_name": a.metric_name,
                "severity": a.severity,
                "baseline_value": a.baseline_value,
                "current_value": a.current_value,
                "difference": a.difference,
                "pct_change": a.pct_change,
                "explanation": a.explanation,
                "suggested_action": a.suggested_action,
                "is_resolved": a.is_resolved,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            })

        out_json = self.output_dir / "alerts_report.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)

        out_csv = self.output_dir / "alerts_report.csv"
        if rows:
            with open(out_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows([sanitize_dict_for_csv(r) for r in rows])

        return str(out_json)

    def generate_rejected_records_report(self, db: Session, run_id: Optional[str] = None) -> str:
        """Export rejected records to CSV and JSON."""
        query = db.query(RejectedRecord)
        if run_id:
            query = query.filter_by(run_id=run_id)
        records = query.order_by(RejectedRecord.rejected_at.desc()).limit(1000).all()

        rows = []
        for r in records:
            rows.append({
                "id": r.id,
                "run_id": r.run_id,
                "source_file": r.source_file,
                "line_number": r.line_number,
                "rejection_code": r.rejection_code,
                "rejection_reason": r.rejection_reason,
                "rejected_at": r.rejected_at.isoformat() if r.rejected_at else "",
            })

        out_json = self.output_dir / "rejected_records_report.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        return str(out_json)

    def generate_baseline_comparison_report(self, db: Session, run_id: Optional[str] = None) -> str:
        """Compare latest or specified run profile with active baseline."""
        baseline = db.query(BaselineProfile).filter_by(is_active=True).first()
        query = db.query(DataQualityProfile)
        if run_id:
            query = query.filter_by(run_id=run_id)
        profile = query.order_by(DataQualityProfile.created_at.desc()).first()

        comparison = {
            "baseline_version": baseline.version if baseline else None,
            "run_id": profile.run_id if profile else None,
            "metrics": {}
        }

        if baseline and profile:
            metrics_to_compare = ["batch_volume", "null_rate", "mean_amount", "min_amount", "max_amount"]
            for m in metrics_to_compare:
                b_val = getattr(baseline, "record_volume" if m == "batch_volume" else m, 0.0)
                p_val = getattr(profile, m, 0.0)
                diff = p_val - b_val
                pct = (diff / b_val * 100.0) if b_val != 0 else 0.0
                comparison["metrics"][m] = {
                    "baseline": b_val,
                    "current": p_val,
                    "difference": round(diff, 2),
                    "pct_change": round(pct, 2),
                }

        out_json = self.output_dir / "baseline_comparison_report.json"
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2)
        return str(out_json)
