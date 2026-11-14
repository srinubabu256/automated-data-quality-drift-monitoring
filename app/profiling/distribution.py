"""Distribution profiling and drift analysis comparing numeric metrics against baselines."""
from typing import Any, Dict, List, Optional
import numpy as np


class DistributionCalculator:
    """Calculates summary statistics and quantiles for numeric distributions."""

    @staticmethod
    def calculate_numeric_summary(values: List[float]) -> Dict[str, float]:
        """
        Calculate mean, std, min, max, median (p50), and p95 for a list of numeric values.
        Returns all zeros if list is empty.
        """
        if not values:
            return {
                "mean": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0,
                "median": 0.0,
                "p95": 0.0,
            }

        arr = np.array(values, dtype=np.float64)
        mean_val = float(np.mean(arr))
        std_val = float(np.std(arr))
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        median_val = float(np.median(arr))
        p95_val = float(np.percentile(arr, 95))

        return {
            "mean": round(mean_val, 2),
            "std": round(std_val, 2),
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "median": round(median_val, 2),
            "p95": round(p95_val, 2),
        }


class DistributionAnalyzer:
    """Computes drifts and relative shifts between current batch metrics and baselines."""

    @staticmethod
    def compute_relative_drift(current_val: float, baseline_val: float) -> Dict[str, float]:
        """Calculates absolute difference and percentage change."""
        diff = current_val - baseline_val
        if baseline_val == 0.0:
            pct_change = 100.0 if current_val > 0.0 else 0.0
        else:
            pct_change = (diff / baseline_val) * 100.0

        return {
            "baseline": float(baseline_val),
            "current": float(current_val),
            "difference": round(float(diff), 4),
            "pct_change": round(float(pct_change), 2),
        }

    @staticmethod
    def compute_percentage_point_shift(current_rate: float, baseline_rate: float) -> Dict[str, float]:
        """Computes percentage point difference for rate metrics (such as null rate)."""
        pp_shift = (current_rate - baseline_rate) * 100.0
        return {
            "baseline_rate_pct": round(baseline_rate * 100.0, 2),
            "current_rate_pct": round(current_rate * 100.0, 2),
            "percentage_point_diff": round(pp_shift, 2),
        }
