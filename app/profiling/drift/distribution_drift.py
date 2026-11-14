"""Distribution Drift Detection Module implementing PSI, Kolmogorov-Smirnov, and Chi-Square tests."""
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from app.config import settings
from app.models.enums import AlertSeverity, DetectionMethod, DriftType

logger = logging.getLogger("distribution_drift")


# ---------------------------------------------------------------------------
# Pure Statistical Helpers (Self-Contained, Zero Binary Mismatch Risk)
# ---------------------------------------------------------------------------

def _gammp(a: float, x: float) -> float:
    """Incomplete gamma function P(a, x) via series or continued fraction."""
    if x <= 0.0 or a <= 0.0:
        return 0.0
    if x < a + 1.0:
        ap = a
        sum_val = del_val = 1.0 / a
        for _ in range(120):
            ap += 1.0
            del_val *= x / ap
            sum_val += del_val
            if abs(del_val) < abs(sum_val) * 1e-12:
                break
        return sum_val * math.exp(-x + a * math.log(x) - math.lgamma(a))
    else:
        b = x + 1.0 - a
        c = 1.0 / 1e-30
        d = 1.0 / b
        h = d
        for i in range(1, 121):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < 1e-30:
                d = 1e-30
            c = b + an / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            del_val = d * c
            h *= del_val
            if abs(del_val - 1.0) < 1e-12:
                break
        return 1.0 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def _chi2_p_value(chi2: float, df: int) -> float:
    """Calculates right-tail p-value for Chi-Square distribution."""
    if df <= 0 or chi2 <= 0.0:
        return 1.0
    p = 1.0 - _gammp(df / 2.0, chi2 / 2.0)
    return max(0.0, min(1.0, float(p)))


def _ks_two_sample(sample1: List[float], sample2: List[float]) -> Tuple[float, float]:
    """
    Computes two-sample Kolmogorov-Smirnov statistic D and asymptotic p-value.
    Equivalent to scipy.stats.ks_2samp with Stephens asymptotic approximation.
    """
    n1 = len(sample1)
    n2 = len(sample2)
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0

    s1 = np.sort(np.asarray(sample1, dtype=np.float64))
    s2 = np.sort(np.asarray(sample2, dtype=np.float64))

    all_vals = np.concatenate([s1, s2])
    all_vals.sort()

    # Empirical CDFs
    cdf1 = np.searchsorted(s1, all_vals, side="right") / n1
    cdf2 = np.searchsorted(s2, all_vals, side="right") / n2

    d_stat = float(np.max(np.abs(cdf1 - cdf2)))

    # Effective sample size and asymptotic p-value
    en = math.sqrt((n1 * n2) / (n1 + n2))
    if en <= 0.0 or d_stat <= 0.0:
        return round(d_stat, 4), 1.0

    lam = (en + 0.12 + 0.11 / en) * d_stat
    p_val = 2.0 * sum((-1.0) ** (k - 1) * math.exp(-2.0 * (k ** 2) * (lam ** 2)) for k in range(1, 40))
    p_val = max(0.0, min(1.0, float(p_val)))

    return round(d_stat, 4), round(p_val, 4)


# ---------------------------------------------------------------------------
# Distribution Drift Detector
# ---------------------------------------------------------------------------

class DistributionDriftDetector:
    """
    Evaluates distribution drift across numerical and categorical features.
    Applies PSI, Kolmogorov-Smirnov (KS), and Chi-Square tests based on column type.
    """

    IDENTIFIER_COLUMNS = {
        "event_id", "transaction_id", "customer_id", "product_id",
        "id", "uuid", "hash", "file_hash", "source_file"
    }

    DATETIME_COLUMNS = {
        "event_timestamp", "ingestion_timestamp", "created_at", "updated_at",
        "start_time", "end_time", "applied_at", "rejected_at"
    }

    NUMERIC_COLUMNS = {"amount", "price", "duration_sec", "total_amount", "current_amount"}

    @classmethod
    def is_identifier(cls, col_name: str) -> bool:
        """Determines if a column is an identifier that must be excluded from statistical drift tests."""
        name_lower = col_name.lower().strip()
        if name_lower in cls.IDENTIFIER_COLUMNS or name_lower.endswith("_id"):
            return True
        return False

    @classmethod
    def is_datetime(cls, col_name: str) -> bool:
        """Determines if a column is a timestamp/datetime column."""
        name_lower = col_name.lower().strip()
        if name_lower in cls.DATETIME_COLUMNS or "time" in name_lower or "date" in name_lower:
            return True
        return False

    # -----------------------------------------------------------------------
    # Method 1: Population Stability Index (PSI)
    # -----------------------------------------------------------------------

    @classmethod
    def calculate_numeric_psi(
        cls,
        current_values: List[float],
        baseline_values: Optional[List[float]] = None,
        baseline_bins: Optional[List[float]] = None,
        baseline_proportions: Optional[List[float]] = None,
        num_bins: int = 5,
        epsilon: float = 1e-4,
    ) -> Dict[str, Any]:
        """
        Calculates Population Stability Index for continuous numerical data.

        Formula:
            PSI = sum((current_pct - baseline_pct) * ln(current_pct / baseline_pct))
        """
        clean_curr = [float(x) for x in current_values if x is not None and not np.isnan(x)]
        if not clean_curr:
            return {
                "psi": 0.0,
                "drift_detected": False,
                "severity": "NONE",
                "details": "Current sample is empty or contains only non-finite values."
            }

        # Derive bins from baseline values if available
        if baseline_bins is None:
            if baseline_values and len(baseline_values) >= 5:
                clean_base = [float(x) for x in baseline_values if x is not None and not np.isnan(x)]
                quantiles = np.linspace(0, 100, num_bins + 1)
                baseline_bins = list(np.percentile(clean_base, quantiles))
                # Ensure strictly increasing bins
                for i in range(1, len(baseline_bins)):
                    if baseline_bins[i] <= baseline_bins[i - 1]:
                        baseline_bins[i] = baseline_bins[i - 1] + 1e-5
            else:
                # Default bins from current data range if baseline array omitted
                c_min, c_max = float(min(clean_curr)), float(max(clean_curr))
                if c_min == c_max:
                    baseline_bins = [c_min - 1.0, c_max + 1.0]
                else:
                    baseline_bins = list(np.linspace(c_min, c_max, num_bins + 1))

        if baseline_proportions is None:
            if baseline_values and len(baseline_values) > 0:
                clean_base = [float(x) for x in baseline_values if x is not None and not np.isnan(x)]
                b_counts, _ = np.histogram(clean_base, bins=baseline_bins)
                b_total = len(clean_base)
                baseline_proportions = [(c / b_total) for c in b_counts]
            else:
                # Uniform baseline expectation
                k = len(baseline_bins) - 1
                baseline_proportions = [1.0 / k] * k

        # Current bin counts
        c_counts, _ = np.histogram(clean_curr, bins=baseline_bins)
        c_total = len(clean_curr)
        current_proportions = [(c / c_total) for c in c_counts]

        # Calculate PSI with numerical stability protection epsilon
        psi_total = 0.0
        bin_details = []
        for i in range(len(baseline_proportions)):
            p_base = max(baseline_proportions[i], epsilon)
            p_curr = max(current_proportions[i], epsilon)
            bin_psi = (p_curr - p_base) * math.log(p_curr / p_base)
            psi_total += bin_psi
            bin_details.append({
                "bin_range": f"[{baseline_bins[i]:.2f}, {baseline_bins[i+1]:.2f})",
                "baseline_pct": round(p_base * 100.0, 2),
                "current_pct": round(p_curr * 100.0, 2),
                "bin_psi": round(bin_psi, 4),
            })

        psi_val = round(float(psi_total), 4)

        # Severity mapping
        if psi_val >= settings.DRIFT_PSI_CRITICAL:
            severity = AlertSeverity.CRITICAL.value
            drift_detected = True
        elif psi_val >= settings.DRIFT_PSI_SIGNIFICANT:
            severity = AlertSeverity.HIGH.value
            drift_detected = True
        elif psi_val >= settings.DRIFT_PSI_MODERATE:
            severity = AlertSeverity.MEDIUM.value
            drift_detected = True
        else:
            severity = "NONE"
            drift_detected = False

        return {
            "psi": psi_val,
            "drift_detected": drift_detected,
            "severity": severity,
            "bins": baseline_bins,
            "bin_details": bin_details,
        }

    @classmethod
    def calculate_categorical_psi(
        cls,
        current_categories: List[str],
        baseline_frequencies: Dict[str, Union[int, float]],
        epsilon: float = 1e-4,
    ) -> Dict[str, Any]:
        """
        Calculates Population Stability Index for categorical features.
        Handles new categories and disappearing categories without silently discarding them.
        """
        curr_counts: Dict[str, int] = {}
        for c in current_categories:
            val_str = str(c).strip() if c is not None else "NULL"
            curr_counts[val_str] = curr_counts.get(val_str, 0) + 1

        curr_total = sum(curr_counts.values())
        if curr_total == 0:
            return {
                "psi": 0.0,
                "drift_detected": False,
                "severity": "NONE",
                "details": "Current categorical sample is empty.",
                "category_details": {},
            }

        base_total = sum(baseline_frequencies.values())
        if base_total == 0:
            base_total = 1.0

        # Full union of categories from both baseline and current batch
        all_categories = sorted(list(set(curr_counts.keys()).union(set(baseline_frequencies.keys()))))

        psi_total = 0.0
        cat_details = {}
        for cat in all_categories:
            base_cnt = baseline_frequencies.get(cat, 0.0)
            curr_cnt = curr_counts.get(cat, 0)

            p_base = (base_cnt / base_total) if base_total > 0 else epsilon
            p_curr = (curr_cnt / curr_total) if curr_total > 0 else epsilon

            p_base = max(p_base, epsilon)
            p_curr = max(p_curr, epsilon)

            cat_psi = (p_curr - p_base) * math.log(p_curr / p_base)
            psi_total += cat_psi

            cat_details[cat] = {
                "baseline_pct": round(p_base * 100.0, 2),
                "current_pct": round(p_curr * 100.0, 2),
                "shift_pp": round((p_curr - p_base) * 100.0, 2),
                "is_new_category": cat not in baseline_frequencies,
                "is_disappeared": cat not in curr_counts,
                "cat_psi": round(cat_psi, 4),
            }

        psi_val = round(float(psi_total), 4)

        if psi_val >= settings.DRIFT_PSI_CRITICAL:
            severity = AlertSeverity.CRITICAL.value
            drift_detected = True
        elif psi_val >= settings.DRIFT_PSI_SIGNIFICANT:
            severity = AlertSeverity.HIGH.value
            drift_detected = True
        elif psi_val >= settings.DRIFT_PSI_MODERATE:
            severity = AlertSeverity.MEDIUM.value
            drift_detected = True
        else:
            severity = "NONE"
            drift_detected = False

        return {
            "psi": psi_val,
            "drift_detected": drift_detected,
            "severity": severity,
            "category_details": cat_details,
        }

    # -----------------------------------------------------------------------
    # Method 2: Kolmogorov-Smirnov (KS) Two-Sample Test
    # -----------------------------------------------------------------------

    @classmethod
    def calculate_ks_test(
        cls,
        current_sample: List[float],
        baseline_sample: List[float],
        alpha: Optional[float] = None,
        min_sample_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Executes two-sample Kolmogorov-Smirnov test for continuous numeric distributions.
        """
        sig_level = alpha if alpha is not None else settings.DRIFT_KS_PVALUE_THRESHOLD
        min_n = min_sample_size if min_sample_size is not None else settings.DRIFT_MIN_SAMPLE_SIZE

        # Filter out nulls and non-finite numbers
        clean_curr = [float(x) for x in current_sample if x is not None and not np.isnan(x)]
        clean_base = [float(x) for x in baseline_sample if x is not None and not np.isnan(x)]

        # Check sample size requirements
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

        # Check for zero variance (constant numerical columns)
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

        ks_stat, p_val = _ks_two_sample(clean_curr, clean_base)
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

    # -----------------------------------------------------------------------
    # Method 3: Chi-Square Test
    # -----------------------------------------------------------------------

    @classmethod
    def calculate_chisquare_test(
        cls,
        current_categories: List[str],
        baseline_frequencies: Dict[str, Union[int, float]],
        alpha: Optional[float] = None,
        min_expected_count: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Executes Chi-Square goodness-of-fit test comparing observed frequencies to expected baseline.
        """
        sig_level = alpha if alpha is not None else settings.DRIFT_CHISQUARE_PVALUE_THRESHOLD
        min_exp = min_expected_count if min_expected_count is not None else settings.DRIFT_CHISQUARE_MIN_EXPECTED_COUNT

        curr_counts: Dict[str, int] = {}
        for c in current_categories:
            val_str = str(c).strip() if c is not None else "NULL"
            curr_counts[val_str] = curr_counts.get(val_str, 0) + 1

        n_curr = sum(curr_counts.values())
        if n_curr < 10:
            return {
                "applicable": False,
                "reason": f"Insufficient categorical sample size (N={n_curr} < 10).",
                "statistic": None,
                "degrees_of_freedom": None,
                "p_value": None,
                "drift_detected": False,
            }

        base_total = sum(baseline_frequencies.values())
        if base_total == 0:
            return {
                "applicable": False,
                "reason": "Baseline frequency total is zero.",
                "statistic": None,
                "degrees_of_freedom": None,
                "p_value": None,
                "drift_detected": False,
            }

        all_categories = sorted(list(set(curr_counts.keys()).union(set(baseline_frequencies.keys()))))
        if len(all_categories) < 2:
            return {
                "applicable": False,
                "reason": "At least two categories required for Chi-Square comparison.",
                "statistic": None,
                "degrees_of_freedom": None,
                "p_value": None,
                "drift_detected": False,
            }

        observed = []
        expected = []
        sparse_cells = 0

        for cat in all_categories:
            obs = curr_counts.get(cat, 0)
            base_prop = (baseline_frequencies.get(cat, 0.0) / base_total) if base_total > 0 else 0.0
            # Small smoothing prior for unseen categories to prevent zero division
            base_prop = max(base_prop, 1e-4)
            exp = n_curr * base_prop

            observed.append(obs)
            expected.append(exp)
            if exp < min_exp:
                sparse_cells += 1

        # Rescale expected to sum exactly to sum(observed)
        sum_obs = sum(observed)
        sum_exp = sum(expected)
        expected = [e * (sum_obs / sum_exp) for e in expected]

        # Check Cochran's assumption: at most 20% of expected cells < 5
        pct_sparse = (sparse_cells / len(all_categories)) * 100.0
        assumptions_satisfied = pct_sparse <= 20.0

        # Calculate Chi-Square statistic
        chi2_stat = 0.0
        for obs, exp in zip(observed, expected):
            if exp > 0:
                chi2_stat += ((obs - exp) ** 2) / exp

        df = len(all_categories) - 1
        p_val = _chi2_p_value(chi2_stat, df)
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

    # -----------------------------------------------------------------------
    # Comprehensive Column Evaluator
    # -----------------------------------------------------------------------

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
        """
        Evaluates distribution drift for a column using the appropriate statistical test selection rules.
        """
        # Rule 1: Exclude identifiers
        if cls.is_identifier(column_name):
            return {
                "column_name": column_name,
                "column_type": "IDENTIFIER",
                "test_applied": "NONE",
                "drift_detected": False,
                "reason": f"Column '{column_name}' is an identifier/key and excluded from distribution drift.",
                "alerts": [],
            }

        # Rule 2: Exclude datetimes
        if cls.is_datetime(column_name):
            return {
                "column_name": column_name,
                "column_type": "DATETIME",
                "test_applied": "NONE",
                "drift_detected": False,
                "reason": f"Column '{column_name}' is a datetime and excluded by default from distribution drift.",
                "alerts": [],
            }

        # Determine if continuous numeric or categorical
        is_numeric = False
        numeric_vals = []
        for v in current_values:
            if v is not None and str(v).strip() != "" and str(v).lower() != "nan":
                try:
                    numeric_vals.append(float(v))
                except (ValueError, TypeError):
                    break
        else:
            if len(numeric_vals) > 0 and column_name in cls.NUMERIC_COLUMNS:
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

        # -------------------------------------------------------------------
        # Continuous Numeric Evaluation: PSI + KS-test
        # -------------------------------------------------------------------
        if is_numeric:
            base_values = baseline_data.get("values") if baseline_data else None
            base_bins = baseline_data.get("bins") if baseline_data else None
            base_props = baseline_data.get("proportions") if baseline_data else None

            # 1. Numerical PSI
            psi_res = cls.calculate_numeric_psi(
                current_values=numeric_vals,
                baseline_values=base_values,
                baseline_bins=base_bins,
                baseline_proportions=base_props,
            )
            results["psi_result"] = psi_res

            # 2. KS Test
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

        # -------------------------------------------------------------------
        # Categorical Evaluation: Categorical PSI + Chi-Square
        # -------------------------------------------------------------------
        else:
            cat_strings = [str(x).strip() for x in current_values if x is not None]
            base_frequencies = baseline_data.get("frequencies", {}) if baseline_data else {}

            # 1. Categorical PSI
            psi_res = cls.calculate_categorical_psi(
                current_categories=cat_strings,
                baseline_frequencies=base_frequencies,
            )
            results["psi_result"] = psi_res

            # 2. Chi-Square Test
            chi_res = cls.calculate_chisquare_test(
                current_categories=cat_strings,
                baseline_frequencies=base_frequencies,
            )
            results["chisquare_result"] = chi_res

            if psi_res["drift_detected"]:
                results["drift_detected"] = True
                results["severity"] = psi_res["severity"]

                # Highlight new or shifted categories
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
