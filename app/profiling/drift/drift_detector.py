"""Unified Drift Orchestrator for YottaFlex Automated Data Quality & Drift Monitoring."""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

from app.config import settings
from app.models.database_models import (
    BaselineProfile,
    DataQualityAlert,
    DriftAnalysisResult,
    ProcessingRun,
)
from app.models.enums import AlertSeverity, DetectionMethod, DriftType
from app.profiling.baseline import BaselineManager
from app.profiling.drift.distribution_drift import DistributionDriftDetector
from app.profiling.drift.null_drift import NullRateDriftDetector
from app.profiling.drift.volume_drift import VolumeDriftDetector

logger = logging.getLogger("drift_detector")

SEVERITY_ORDER = {
    "CRITICAL": 5,
    "HIGH": 4,
    "WARNING": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "NONE": 0,
}


class DriftDetector:
    """
    Unified drift detection coordinator executing:
      1. Volume Drift (Record counts, percentage spikes/drops)
      2. Null-Rate Drift (Column-level percentage point shifts)
      3. Distribution Drift (Continuous PSI + KS, Categorical PSI + Chi-Square)
    """

    @classmethod
    def analyze(
        cls,
        records: Any,
        baseline_profile: Optional[Union[BaselineProfile, Dict[str, Any]]] = None,
        run_id: str = "RUN_ADHOC",
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
        db: Optional[Session] = None,
        save_results: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes complete multi-dimensional drift detection across volume, nulls, and distributions.
        Persists results and explainable alerts into the relational database when db session is supplied.
        """
        # Normalize input records to list of dicts
        records_list: List[Dict[str, Any]] = []
        if records is not None:
            if hasattr(records, "to_dict"):
                records_list = records.to_dict(orient="records")
            elif isinstance(records, list):
                records_list = records
            else:
                try:
                    records_list = list(records)
                except Exception:
                    records_list = []

        # Resolve baseline profile
        active_baseline = baseline_profile
        if active_baseline is None and db is not None:
            try:
                active_baseline = BaselineManager.get_active_baseline(db, version=baseline_version)
            except Exception as e:
                logger.warning(f"Could not load active baseline profile: {e}")

        # Extract baseline attributes
        b_version = baseline_version
        b_volume = None
        column_baselines: Dict[str, Any] = {}

        if active_baseline is not None:
            if isinstance(active_baseline, BaselineProfile):
                b_version = active_baseline.version or baseline_version
                b_volume = active_baseline.record_volume
                raw_col_baselines = active_baseline.column_baselines
                if raw_col_baselines:
                    try:
                        column_baselines = json.loads(raw_col_baselines) if isinstance(raw_col_baselines, str) else raw_col_baselines
                    except Exception as e:
                        logger.warning(f"Failed to parse column_baselines JSON: {e}")
            elif isinstance(active_baseline, dict):
                b_version = active_baseline.get("version", baseline_version)
                b_volume = active_baseline.get("record_volume")
                raw_col = active_baseline.get("column_baselines", {})
                if isinstance(raw_col, str):
                    try:
                        column_baselines = json.loads(raw_col)
                    except Exception:
                        column_baselines = {}
                elif isinstance(raw_col, dict):
                    column_baselines = raw_col

        # Build baseline null rates dictionary
        baseline_null_rates: Dict[str, float] = {}
        for col_name, c_info in column_baselines.items():
            if isinstance(c_info, dict):
                if "null_rate" in c_info:
                    baseline_null_rates[col_name] = float(c_info["null_rate"])
                elif "null_percentage" in c_info:
                    baseline_null_rates[col_name] = float(c_info["null_percentage"])

        # -------------------------------------------------------------------
        # 1. Volume Drift Evaluation
        # -------------------------------------------------------------------
        volume_res = VolumeDriftDetector.evaluate(
            current_count=len(records_list),
            baseline_count=b_volume,
            run_id=run_id,
            baseline_version=b_version,
            dataset_name=dataset_name,
        )

        # -------------------------------------------------------------------
        # 2. Null-Rate Drift Evaluation
        # -------------------------------------------------------------------
        null_res_list = NullRateDriftDetector.evaluate_batch(
            records=records_list,
            baseline_null_rates=baseline_null_rates,
            run_id=run_id,
            baseline_version=b_version,
            dataset_name=dataset_name,
        )

        # -------------------------------------------------------------------
        # 3. Distribution Drift Evaluation
        # -------------------------------------------------------------------
        dist_res_list = []
        # Discover all unique columns from incoming records and baseline
        discovered_cols = set()
        for r in records_list:
            discovered_cols.update(r.keys())
        discovered_cols.update(column_baselines.keys())

        for col in sorted(list(discovered_cols)):
            # Respect Test Selection Matrix: exclude identifiers and datetimes
            if DistributionDriftDetector.is_identifier(col):
                continue
            if DistributionDriftDetector.is_datetime(col):
                continue

            col_vals = [r.get(col) for r in records_list if col in r]
            col_bdata = column_baselines.get(col)

            col_dist_res = DistributionDriftDetector.evaluate_column(
                column_name=col,
                current_values=col_vals,
                baseline_data=col_bdata,
                run_id=run_id,
                baseline_version=b_version,
                dataset_name=dataset_name,
            )
            dist_res_list.append(col_dist_res)

        # -------------------------------------------------------------------
        # 4. Aggregation and Alert Consolidation
        # -------------------------------------------------------------------
        collected_alerts: List[Dict[str, Any]] = []
        drift_results_to_save: List[Dict[str, Any]] = []

        # Add volume drift result & alert
        drift_results_to_save.append({
            "run_id": run_id,
            "baseline_version": b_version,
            "drift_type": volume_res["drift_type"],
            "column_name": volume_res["column_name"],
            "detection_method": volume_res["detection_method"],
            "baseline_value": volume_res["baseline_value"],
            "current_value": volume_res["current_value"],
            "absolute_difference": volume_res["absolute_difference"],
            "percentage_difference": volume_res["percentage_difference"],
            "statistical_statistic": volume_res["statistical_statistic"],
            "p_value": volume_res["p_value"],
            "degrees_of_freedom": volume_res["degrees_of_freedom"],
            "drift_detected": volume_res["drift_detected"],
            "severity": volume_res["severity"],
            "threshold": volume_res["configured_threshold"],
            "details": volume_res["details"],
        })
        if volume_res.get("alert"):
            collected_alerts.append(volume_res["alert"])

        # Add null-rate drift results & alerts
        for n_res in null_res_list:
            drift_results_to_save.append({
                "run_id": run_id,
                "baseline_version": b_version,
                "drift_type": n_res["drift_type"],
                "column_name": n_res["column_name"],
                "detection_method": n_res["detection_method"],
                "baseline_value": n_res["baseline_value"],
                "current_value": n_res["current_value"],
                "absolute_difference": n_res["absolute_difference"],
                "percentage_difference": n_res["percentage_difference"],
                "statistical_statistic": n_res["statistical_statistic"],
                "p_value": n_res["p_value"],
                "degrees_of_freedom": n_res["degrees_of_freedom"],
                "drift_detected": n_res["drift_detected"],
                "severity": n_res["severity"],
                "threshold": n_res["configured_threshold"],
                "details": n_res["details"],
            })
            if n_res.get("alert"):
                collected_alerts.append(n_res["alert"])

        # Add distribution drift results & alerts
        for d_res in dist_res_list:
            col_name = d_res["column_name"]
            # 1. PSI Result
            psi_info = d_res.get("psi_result", {})
            if psi_info:
                drift_results_to_save.append({
                    "run_id": run_id,
                    "baseline_version": b_version,
                    "drift_type": DriftType.DISTRIBUTION_PSI.value,
                    "column_name": col_name,
                    "detection_method": DetectionMethod.PSI.value,
                    "baseline_value": None,
                    "current_value": None,
                    "absolute_difference": None,
                    "percentage_difference": None,
                    "statistical_statistic": psi_info.get("psi"),
                    "p_value": None,
                    "degrees_of_freedom": None,
                    "drift_detected": psi_info.get("drift_detected", False),
                    "severity": psi_info.get("severity", "NONE"),
                    "threshold": psi_info.get("threshold"),
                    "details": psi_info.get("interpretation", ""),
                })

            # 2. Continuous KS Result
            ks_info = d_res.get("ks_result", {})
            if ks_info and ks_info.get("applicable"):
                drift_results_to_save.append({
                    "run_id": run_id,
                    "baseline_version": b_version,
                    "drift_type": DriftType.DISTRIBUTION_KS.value,
                    "column_name": col_name,
                    "detection_method": DetectionMethod.KOLMOGOROV_SMIRNOV.value,
                    "baseline_value": None,
                    "current_value": None,
                    "absolute_difference": None,
                    "percentage_difference": None,
                    "statistical_statistic": ks_info.get("statistic"),
                    "p_value": ks_info.get("p_value"),
                    "degrees_of_freedom": None,
                    "drift_detected": ks_info.get("drift_detected", False),
                    "severity": AlertSeverity.WARNING.value if ks_info.get("drift_detected") else "NONE",
                    "threshold": ks_info.get("alpha"),
                    "details": ks_info.get("interpretation", ""),
                })

            # 3. Categorical Chi-Square Result
            chi_info = d_res.get("chisquare_result", {})
            if chi_info and chi_info.get("applicable"):
                drift_results_to_save.append({
                    "run_id": run_id,
                    "baseline_version": b_version,
                    "drift_type": DriftType.DISTRIBUTION_CHISQUARE.value,
                    "column_name": col_name,
                    "detection_method": DetectionMethod.CHI_SQUARE.value,
                    "baseline_value": None,
                    "current_value": None,
                    "absolute_difference": None,
                    "percentage_difference": None,
                    "statistical_statistic": chi_info.get("statistic"),
                    "p_value": chi_info.get("p_value"),
                    "degrees_of_freedom": chi_info.get("degrees_of_freedom"),
                    "drift_detected": chi_info.get("drift_detected", False),
                    "severity": AlertSeverity.WARNING.value if chi_info.get("drift_detected") else "NONE",
                    "threshold": chi_info.get("alpha"),
                    "details": chi_info.get("interpretation", ""),
                })

            # Collect distribution alerts
            for alt in d_res.get("alerts", []):
                collected_alerts.append(alt)

        # Compute overall drift detected and maximum severity
        drift_detected = (
            volume_res.get("drift_detected", False)
            or any(n.get("drift_detected", False) for n in null_res_list)
            or any(d.get("drift_detected", False) for d in dist_res_list)
        )

        max_sev_score = 0
        highest_severity = "NONE"
        for alt in collected_alerts:
            sev_str = str(alt.get("severity", "NONE")).upper()
            score = SEVERITY_ORDER.get(sev_str, 0)
            if score > max_sev_score:
                max_sev_score = score
                highest_severity = sev_str

        # -------------------------------------------------------------------
        # 5. Database Persistence & Deduplication
        # -------------------------------------------------------------------
        persisted_results = 0
        persisted_alerts = 0

        if db is not None and save_results:
            try:
                # Ensure processing_runs entry exists to satisfy FK constraint
                run_obj = db.query(ProcessingRun).filter_by(run_id=run_id).first()
                if not run_obj:
                    run_obj = ProcessingRun(
                        run_id=run_id,
                        source_file=f"drift_batch_{run_id}.csv",
                        file_hash=f"hash_{run_id}",
                        status="COMPLETED",
                        input_count=len(records_list),
                        start_time=datetime.now(timezone.utc),
                        end_time=datetime.now(timezone.utc),
                    )
                    db.add(run_obj)
                    db.flush()

                # Persist DriftAnalysisResult records
                for r_data in drift_results_to_save:
                    drift_row = DriftAnalysisResult(
                        run_id=r_data["run_id"],
                        baseline_version=r_data["baseline_version"],
                        drift_type=r_data["drift_type"],
                        column_name=r_data["column_name"],
                        detection_method=r_data["detection_method"],
                        baseline_value=r_data["baseline_value"],
                        current_value=r_data["current_value"],
                        absolute_difference=r_data["absolute_difference"],
                        percentage_difference=r_data["percentage_difference"],
                        statistical_statistic=r_data["statistical_statistic"],
                        p_value=r_data["p_value"],
                        degrees_of_freedom=r_data["degrees_of_freedom"],
                        drift_detected=r_data["drift_detected"],
                        severity=r_data["severity"],
                        threshold=r_data["threshold"],
                        details=r_data["details"],
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(drift_row)
                    persisted_results += 1

                # Persist DataQualityAlert records with deduplication
                seen_metric_names = set()
                for a_data in collected_alerts:
                    metric_name = a_data["metric_name"]
                    if metric_name in seen_metric_names:
                        continue
                    seen_metric_names.add(metric_name)

                    # Check DB for existing alert on (run_id, metric_name)
                    existing_alert = (
                        db.query(DataQualityAlert)
                        .filter_by(run_id=run_id, metric_name=metric_name)
                        .first()
                    )
                    if existing_alert:
                        continue

                    new_alert = DataQualityAlert(
                        alert_id=a_data["alert_id"],
                        run_id=run_id,
                        dataset_name=a_data.get("dataset_name", dataset_name),
                        column_name=a_data.get("column_name"),
                        drift_type=a_data.get("drift_type"),
                        metric_name=metric_name,
                        detection_method=a_data.get("detection_method"),
                        baseline_value=float(a_data.get("baseline_value") if a_data.get("baseline_value") is not None else 0.0),
                        current_value=float(a_data.get("current_value") if a_data.get("current_value") is not None else 0.0),
                        difference=float(a_data.get("absolute_difference") if a_data.get("absolute_difference") is not None else 0.0),
                        pct_change=float(a_data.get("percentage_difference") if a_data.get("percentage_difference") is not None else 0.0),
                        statistical_statistic=a_data.get("statistical_statistic"),
                        p_value=a_data.get("p_value"),
                        configured_threshold=a_data.get("configured_threshold"),
                        severity=a_data.get("severity", "WARNING"),
                        explanation=a_data.get("explanation", ""),
                        suggested_action=a_data.get("recommended_action", a_data.get("suggested_action", "")),
                        is_resolved=False,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(new_alert)
                    persisted_alerts += 1

                db.commit()
                logger.info(
                    f"Drift analysis saved for run {run_id}: {persisted_results} results, {persisted_alerts} alerts."
                )
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to persist drift analysis for run {run_id}: {e}", exc_info=True)

        return {
            "run_id": run_id,
            "dataset_name": dataset_name,
            "baseline_version": b_version,
            "record_count": len(records_list),
            "drift_detected": drift_detected,
            "highest_severity": highest_severity,
            "volume_drift": volume_res,
            "null_rate_drift": null_res_list,
            "distribution_drift": dist_res_list,
            "drift_results": drift_results_to_save,
            "alerts": collected_alerts,
            "persisted_results_count": persisted_results,
            "persisted_alerts_count": persisted_alerts,
        }
