"""Distribution Drift Detection Module for YottaFlex Platform."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union
import numpy as np

from app.config import settings
from app.database.enums import AlertSeverity, DetectionMethod, DriftType
from app.drift.statistical_tests import (
    calculate_categorical_psi,
    calculate_numeric_psi,
    chi2_p_value,
    ks_two_sample,
)

logger = logging.getLogger("drift.distribution")


class DistributionDriftDetector:
    """
    Evaluates distribution drift across numerical and categorical features.
    Enforces the Statistical Test Selection Matrix.
    """

    IDENTIFIER_COLUMNS: Set[str] = {
        "event_id",
        "transaction_id",
        "customer_id",
        "product_id",
        "user_id",
        "order_id",
        "id",
    }

    DATETIME_COLUMNS: Set[str] = {
        "event_timestamp",
        "ingestion_timestamp",
        "created_at",
        "updated_at",
        "timestamp",
    }

    NUMERIC_COLUMNS: Set[str] = {
        "amount",
        "current_amount",
        "previous_amount",
        "new_amount",
        "total_amount",
        "avg_amount",
        "price",
        "quantity",
    }

    @classmethod
    def is_identifier(cls, column_name: str) -> bool:
        low = column_name.lower()
        return low.endswith("_id") or low in cls.IDENTIFIER_COLUMNS

    @classmethod
    def is_datetime(cls, column_name: str) -> bool:
        low = column_name.lower()
        return "timestamp" in low or low.endswith("_at") or low in cls.DATETIME_COLUMNS

    @classmethod
    def calculate_numeric_psi(
        cls,
        current_values: List[float],
        baseline_values: Optional[List[float]] = None,
        baseline_bins: Optional[List[float]] = None,
        baseline_proportions: Optional[List[float]] = None,
        num_bins: int = 10,
        epsilon: float = 1e-4,
    ) -> Dict[str, Any]:
        return calculate_numeric_psi(
            current_values=current_values,
            baseline_values=baseline_values,
            baseline_bins=baseline_bins,
            baseline_proportions=baseline_proportions,
            num_bins=num_bins,
            epsilon=epsilon,
        )

    @classmethod
    def calculate_categorical_psi(
        cls,
        current_categories: List[str],
        baseline_frequencies: Dict[str, Union[int, float]],
        epsilon: float = 1e-4,
    ) -> Dict[str, Any]:
        return calculate_categorical_psi(
            current_categories=current_categories,
            baseline_frequencies=baseline_frequencies,
            epsilon=epsilon,
        )

    @classmethod
    def calculate_ks_test(
        cls,
        current_sample: List[float],
        baseline_sample: List[float],
        alpha: Optional[float] = None,
        min_sample_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        sig_level = alpha if alpha is not None else settings.DRIFT_KS_PVALUE_THRESHOLD
        min_n = min_sample_size if min_sample_size is not None else settings.DRIFT_MIN_SAMPLE_SIZE

        clean_curr = [float(x) for x in current_sample if x is not None and not np.isnan(x)]
        clean_base = [float(x) for x in baseline_sample if x is not None and not np.isnan(x)]

        if len(clean_curr) < min_n or len(clean_base) < min_n:
            msg = f"Insufficient sample size (Current: {len(clean_curr)}, Baseline: {len(clean_base)}, Minimum required: {min_n})."
            return {
                "applicable": False,
                "reason": msg,
                "interpretation": msg,
                "statistic": None,
                "p_value": None,
                "drift_detected": False,
            }

        if len(set(clean_curr)) <= 1 or len(set(clean_base)) <= 1:
            msg = "Constant numerical column or zero variance in sample."
            return {
                "applicable": False,
                "reason": msg,
                "interpretation": msg,
                "statistic": None,
                "p_value": None,
                "drift_detected": False,
            }

        ks_stat, p_val = ks_two_sample(clean_curr, clean_base)
        statistically_significant = p_val < sig_level

        msg = "Continuous distribution assumption satisfied."
        return {
            "applicable": True,
            "reason": msg,
            "interpretation": msg,
            "statistic": ks_stat,
            "p_value": p_val,
            "alpha": sig_level,
            "drift_detected": statistically_significant,
        }

    @classmethod
    def calculate_chisquare_test(
        cls,
        current_categories: List[str],
        baseline_frequencies: Dict[str, Union[int, float]],
        alpha: Optional[float] = None,
        min_expected_count: Optional[float] = None,
    ) -> Dict[str, Any]:
        sig_level = alpha if alpha is not None else settings.DRIFT_CHISQUARE_PVALUE_THRESHOLD
        min_exp = min_expected_count if min_expected_count is not None else settings.DRIFT_CHISQUARE_MIN_EXPECTED_COUNT

        curr_counts: Dict[str, int] = {}
        for c in current_categories:
            if c is not None and str(c).strip():
                v = str(c).strip()
                curr_counts[v] = curr_counts.get(v, 0) + 1

        n_curr = sum(curr_counts.values())
        if n_curr < settings.DRIFT_MIN_SAMPLE_SIZE:
            msg = f"Insufficient sample size ({n_curr} < {settings.DRIFT_MIN_SAMPLE_SIZE})."
            return {
                "applicable": False,
                "reason": msg,
                "interpretation": msg,
                "statistic": None,
                "p_value": None,
                "degrees_of_freedom": None,
                "drift_detected": False,
            }

        base_total = sum(baseline_frequencies.values()) if baseline_frequencies else 0.0
        all_categories = sorted(list(set(curr_counts.keys()).union(set(baseline_frequencies.keys()))))

        if len(all_categories) <= 1:
            msg = "Chi-Square requires at least two distinct categories."
            return {
                "applicable": False,
                "reason": msg,
                "interpretation": msg,
                "statistic": None,
                "p_value": None,
                "degrees_of_freedom": None,
                "drift_detected": False,
            }

        observed = []
        expected = []
        sparse_cells = 0

        for cat in all_categories:
            obs = curr_counts.get(cat, 0)
            base_prop = (baseline_frequencies.get(cat, 0.0) / base_total) if base_total > 0 else 0.0
            base_prop = max(base_prop, 1e-4)
            exp = n_curr * base_prop
            observed.append(obs)
            expected.append(exp)
            if exp < min_exp:
                sparse_cells += 1

        sum_obs = sum(observed)
        sum_exp = sum(expected)
        expected = [e * (sum_obs / sum_exp) for e in expected]

        pct_sparse = (sparse_cells / len(all_categories)) * 100.0
        assumptions_satisfied = pct_sparse <= 20.0

        chi2_stat = 0.0
        for obs, exp in zip(observed, expected):
            if exp > 0:
                chi2_stat += ((obs - exp) ** 2) / exp

        df = len(all_categories) - 1
        p_val = chi2_p_value(chi2_stat, df)
        statistically_significant = (p_val < sig_level) and assumptions_satisfied

        msg = "Categorical test executed." if assumptions_satisfied else f"Sparse categories detected ({sparse_cells}/{len(all_categories)} expected cells < {min_exp})."
        return {
            "applicable": True,
            "assumptions_satisfied": assumptions_satisfied,
            "reason": msg,
            "interpretation": msg,
            "statistic": round(chi2_stat, 4),
            "degrees_of_freedom": df,
            "p_value": round(p_val, 4),
            "alpha": sig_level,
            "drift_detected": statistically_significant,
        }

    @classmethod
    def evaluate_column(
        cls,
        column_name: str,
        current_values: List[Any],
        baseline_data: Optional[Dict[str, Any]] = None,
        run_id: str = "RUN_ADHOC",
        baseline_version: str = "v1.0",
        dataset_name: str = "transactions",
    ) -> Dict[str, Any]:
        """Evaluates distribution drift according to column classification."""
        if cls.is_identifier(column_name):
            return {
                "column_name": column_name,
                "column_type": "IDENTIFIER",
                "evaluated": False,
                "reason": "Identifier column skipped from distribution testing.",
                "drift_detected": False,
                "severity": "NONE",
                "alerts": [],
            }

        if cls.is_datetime(column_name):
            return {
                "column_name": column_name,
                "column_type": "DATETIME",
                "evaluated": False,
                "reason": "Datetime column skipped from statistical distribution testing.",
                "drift_detected": False,
                "severity": "NONE",
                "alerts": [],
            }

        numeric_vals = []
        is_numeric = False
        for v in current_values:
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                try:
                    numeric_vals.append(float(v))
                except (ValueError, TypeError):
                    pass

        if baseline_data and baseline_data.get("type") == "numeric":
            is_numeric = True
        elif column_name in cls.NUMERIC_COLUMNS and len(numeric_vals) > 0:
            is_numeric = True

        alerts = []
        results: Dict[str, Any] = {
            "column_name": column_name,
            "column_type": "NUMERIC" if is_numeric else "CATEGORICAL",
            "run_id": run_id,
            "baseline_version": baseline_version,
            "dataset_name": dataset_name,
            "drift_detected": False,
            "severity": "NONE",
            "alerts": [],
        }

        if is_numeric:
            base_values = baseline_data.get("values") if baseline_data else None
            base_bins = baseline_data.get("bins") if baseline_data else None
            base_props = baseline_data.get("proportions") if baseline_data else None

            psi_res = cls.calculate_numeric_psi(
                current_values=numeric_vals,
                baseline_values=base_values,
                baseline_bins=base_bins,
                baseline_proportions=base_props,
            )
            results["psi_result"] = psi_res

            ks_res = cls.calculate_ks_test(
                current_sample=numeric_vals,
                baseline_sample=base_values or [],
            )
            results["ks_result"] = ks_res

            if psi_res["drift_detected"]:
                results["drift_detected"] = True
                results["severity"] = psi_res["severity"]

                c_mean = float(np.mean(numeric_vals)) if numeric_vals else 0.0
                b_mean = float(baseline_data.get("mean", 0.0)) if baseline_data else 0.0
                explanation = (
                    f"Numerical distribution drift detected in '{column_name}': PSI={psi_res['psi']:.4f} "
                    f"exceeds threshold (current mean: {c_mean:.2f}, baseline mean: {b_mean:.2f})."
                )
                if ks_res.get("applicable") and ks_res.get("statistic"):
                    explanation += f" KS-test D={ks_res['statistic']:.4f} (p={ks_res['p_value']:.4f})."

                recommended_action = (
                    f"Inspect the distribution of '{column_name}'. Verify transaction value limits, "
                    "currency conversion scaling, or customer mix shifts."
                )

                alert = {
                    "alert_id": f"alt_dist_psi_{column_name}_{uuid.uuid4().hex[:8]}",
                    "batch_id": run_id,
                    "run_id": run_id,
                    "dataset_name": dataset_name,
                    "column_name": column_name,
                    "drift_type": DriftType.DISTRIBUTION_PSI.value,
                    "metric_name": f"distribution_psi:{column_name}",
                    "severity": psi_res["severity"],
                    "baseline_value": b_mean,
                    "current_value": round(c_mean, 2),
                    "absolute_difference": round(c_mean - b_mean, 2),
                    "percentage_difference": round(((c_mean - b_mean) / b_mean * 100.0) if b_mean > 0 else 0.0, 2),
                    "detection_method": DetectionMethod.PSI.value,
                    "statistical_statistic": psi_res["psi"],
                    "p_value": ks_res.get("p_value"),
                    "configured_threshold": settings.DRIFT_PSI_MODERATE,
                    "explanation": explanation,
                    "recommended_action": recommended_action,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                alerts.append(alert)
        else:
            cat_strings = [str(x).strip() for x in current_values if x is not None]
            base_frequencies = baseline_data.get("frequencies", {}) if baseline_data else {}

            psi_res = cls.calculate_categorical_psi(
                current_categories=cat_strings,
                baseline_frequencies=base_frequencies,
            )
            results["psi_result"] = psi_res

            chi_res = cls.calculate_chisquare_test(
                current_categories=cat_strings,
                baseline_frequencies=base_frequencies,
            )
            results["chisquare_result"] = chi_res

            if psi_res["drift_detected"]:
                results["drift_detected"] = True
                results["severity"] = psi_res["severity"]

                new_cats = [k for k, v in psi_res["category_details"].items() if v["is_new_category"]]
                lost_cats = [k for k, v in psi_res["category_details"].items() if v["is_disappeared"]]

                explanation = (
                    f"Categorical distribution drift detected in '{column_name}': PSI={psi_res['psi']:.4f} "
                    f"exceeds threshold of {settings.DRIFT_PSI_MODERATE}."
                )
                if new_cats:
                    explanation += f" Unseen categories observed: {new_cats}."
                if lost_cats:
                    explanation += f" Disappeared categories: {lost_cats}."
                if chi_res.get("applicable") and chi_res.get("statistic"):
                    explanation += f" Chi-Square stat={chi_res['statistic']:.2f} (df={chi_res['degrees_of_freedom']}, p={chi_res['p_value']:.4f})."

                recommended_action = (
                    f"Inspect categorical frequency shifts in '{column_name}'. Verify upstream taxonomy changes, "
                    "new category rollouts, or missing localized partitions."
                )

                alert = {
                    "alert_id": f"alt_dist_cat_{column_name}_{uuid.uuid4().hex[:8]}",
                    "batch_id": run_id,
                    "run_id": run_id,
                    "dataset_name": dataset_name,
                    "column_name": column_name,
                    "drift_type": DriftType.DISTRIBUTION_PSI.value,
                    "metric_name": f"distribution_psi:{column_name}",
                    "severity": psi_res["severity"],
                    "baseline_value": None,
                    "current_value": None,
                    "absolute_difference": None,
                    "percentage_difference": None,
                    "detection_method": DetectionMethod.PSI.value,
                    "statistical_statistic": psi_res["psi"],
                    "p_value": chi_res.get("p_value"),
                    "configured_threshold": settings.DRIFT_PSI_MODERATE,
                    "explanation": explanation,
                    "recommended_action": recommended_action,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                alerts.append(alert)

        results["alerts"] = alerts
        return results
