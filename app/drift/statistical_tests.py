"""Pure mathematical and statistical testing library for drift monitoring.

Includes:
  - Kolmogorov-Smirnov 2-sample test with Stephens asymptotic p-value
  - Chi-Square goodness-of-fit / independence test with incomplete gamma function
  - Population Stability Index (PSI) for continuous numeric distributions
  - Population Stability Index (PSI) for discrete categorical distributions
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from app.config import settings
from app.database.enums import AlertSeverity


# ---------------------------------------------------------------------------
# Regularized Incomplete Gamma Function for Exact Chi-Square p-values
# ---------------------------------------------------------------------------


def _gammp(a: float, x: float) -> float:
    """Returns the regularized incomplete gamma function P(a, x)."""
    if x < 0.0 or a <= 0.0:
        return 0.0
    if x < a + 1.0:
        return _gser(a, x)
    return 1.0 - _gcf(a, x)


def _gser(a: float, x: float, max_iter: int = 150, eps: float = 3e-7) -> float:
    """Series expansion representation of incomplete gamma P(a, x)."""
    if x <= 0.0:
        return 0.0
    gln = math.lgamma(a)
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(max_iter):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * eps:
            return total * math.exp(-x + a * math.log(x) - gln)
    return total * math.exp(-x + a * math.log(x) - gln)


def _gcf(a: float, x: float, max_iter: int = 150, eps: float = 3e-7) -> float:
    """Continued fraction representation of incomplete gamma Q(a, x)."""
    gln = math.lgamma(a)
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


def chi2_p_value(chi2: float, df: int) -> float:
    """Computes exact right-tail p-value: P(X >= chi2) with df degrees of freedom."""
    if chi2 <= 0.0 or df <= 0:
        return 1.0
    a = df / 2.0
    x = chi2 / 2.0
    return max(0.0, min(1.0, 1.0 - _gammp(a, x)))


# ---------------------------------------------------------------------------
# Kolmogorov-Smirnov 2-Sample Test
# ---------------------------------------------------------------------------


def ks_two_sample(sample1: List[float], sample2: List[float]) -> Tuple[float, float]:
    """
    Computes Kolmogorov-Smirnov 2-sample test statistic D and Stephens asymptotic p-value.
    D = sup_x |F1(x) - F2(x)|
    """
    n1 = len(sample1)
    n2 = len(sample2)
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0

    s1 = np.sort(np.asarray(sample1, dtype=float))
    s2 = np.sort(np.asarray(sample2, dtype=float))

    all_vals = np.concatenate([s1, s2])
    all_vals.sort()

    cdf1 = np.searchsorted(s1, all_vals, side="right") / float(n1)
    cdf2 = np.searchsorted(s2, all_vals, side="right") / float(n2)

    d_stat = float(np.max(np.abs(cdf1 - cdf2)))

    # Effective sample size and Stephens asymptotic approximation
    en = math.sqrt((n1 * n2) / (n1 + n2))
    lam = (en + 0.12 + 0.11 / en) * d_stat

    # Kolmogorov distribution asymptotic series
    if lam < 0.2:
        p_val = 1.0
    elif lam > 4.0:
        p_val = 0.0
    else:
        p_sum = 0.0
        for j in range(1, 101):
            term = 2.0 * ((-1) ** (j - 1)) * math.exp(-2.0 * (j ** 2) * (lam ** 2))
            p_sum += term
            if abs(term) < 1e-8:
                break
        p_val = max(0.0, min(1.0, p_sum))

    return round(d_stat, 4), round(p_val, 4)


# ---------------------------------------------------------------------------
# Population Stability Index (Numeric & Categorical)
# ---------------------------------------------------------------------------


def calculate_numeric_psi(
    current_values: List[float],
    baseline_values: Optional[List[float]] = None,
    baseline_bins: Optional[List[float]] = None,
    baseline_proportions: Optional[List[float]] = None,
    num_bins: int = 10,
    epsilon: float = 1e-4,
) -> Dict[str, Any]:
    """Calculates Population Stability Index for continuous numeric features."""
    clean_curr = [float(x) for x in current_values if x is not None and not np.isnan(x)]
    if len(clean_curr) == 0:
        return {
            "psi": 0.0,
            "drift_detected": False,
            "severity": "NONE",
            "threshold": settings.DRIFT_PSI_MODERATE,
            "interpretation": "Current column is empty.",
            "bins": [],
            "bin_details": [],
        }

    # Derive bins from baseline values if bins not explicitly supplied
    if baseline_bins is None:
        if baseline_values and len(baseline_values) > 0:
            clean_base = [float(x) for x in baseline_values if x is not None and not np.isnan(x)]
            percentiles = np.linspace(0, 100, num_bins + 1)
            baseline_bins = list(np.percentile(clean_base, percentiles))
            for i in range(1, len(baseline_bins)):
                if baseline_bins[i] <= baseline_bins[i - 1]:
                    baseline_bins[i] = baseline_bins[i - 1] + 1e-5
        else:
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
            k = len(baseline_bins) - 1
            baseline_proportions = [1.0 / k] * k

    c_counts, _ = np.histogram(clean_curr, bins=baseline_bins)
    c_total = len(clean_curr)
    current_proportions = [(c / c_total) for c in c_counts]

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
        "threshold": settings.DRIFT_PSI_MODERATE,
        "interpretation": f"PSI = {psi_val:.4f} (Severity: {severity})",
        "bins": baseline_bins,
        "bin_details": bin_details,
    }


def calculate_categorical_psi(
    current_categories: List[str],
    baseline_frequencies: Dict[str, Union[int, float]],
    epsilon: float = 1e-4,
) -> Dict[str, Any]:
    """Calculates Population Stability Index for discrete categorical features."""
    curr_counts: Dict[str, int] = {}
    for c in current_categories:
        val_str = str(c).strip() if c is not None else "NULL"
        curr_counts[val_str] = curr_counts.get(val_str, 0) + 1

    total_curr = sum(curr_counts.values())
    if total_curr == 0:
        return {
            "psi": 0.0,
            "drift_detected": False,
            "severity": "NONE",
            "threshold": settings.DRIFT_PSI_MODERATE,
            "interpretation": "Current categorical sample is empty.",
            "category_details": {},
        }

    total_base_freq = sum(baseline_frequencies.values()) if baseline_frequencies else 0.0
    all_categories = sorted(list(set(curr_counts.keys()).union(set(baseline_frequencies.keys()))))

    psi_total = 0.0
    category_details = {}

    for cat in all_categories:
        if total_base_freq > 0 and cat in baseline_frequencies:
            p_base_raw = baseline_frequencies[cat] / total_base_freq
            is_new = False
        else:
            p_base_raw = 0.0
            is_new = True

        if cat in curr_counts:
            p_curr_raw = curr_counts[cat] / total_curr
            is_lost = False
        else:
            p_curr_raw = 0.0
            is_lost = True

        p_base = max(p_base_raw, epsilon)
        p_curr = max(p_curr_raw, epsilon)

        cat_psi = (p_curr - p_base) * math.log(p_curr / p_base)
        psi_total += cat_psi

        category_details[cat] = {
            "baseline_pct": round(p_base_raw * 100.0, 2),
            "current_pct": round(p_curr_raw * 100.0, 2),
            "psi_contribution": round(cat_psi, 4),
            "is_new_category": is_new,
            "is_disappeared": is_lost,
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
        "threshold": settings.DRIFT_PSI_MODERATE,
        "interpretation": f"Categorical PSI = {psi_val:.4f} (Severity: {severity})",
        "category_details": category_details,
    }
