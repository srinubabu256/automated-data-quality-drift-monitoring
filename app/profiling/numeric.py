"""Numeric profiling and distribution calculations."""
import math
from typing import Any, Dict, List
import numpy as np


class NumericProfiler:
    """Computes comprehensive descriptive and distribution metrics for numeric features."""

    @staticmethod
    def calculate_summary(values: List[float], num_bins: int = 10) -> Dict[str, Any]:
        """Calculates mean, std, quantiles, and histogram distribution."""
        clean = [float(v) for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
        if not clean:
            return {
                "count": 0,
                "null_count": len(values) - len(clean),
                "null_rate": 1.0 if values else 0.0,
                "mean": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0,
                "median": 0.0,
                "p25": 0.0,
                "p75": 0.0,
                "p95": 0.0,
                "iqr": 0.0,
                "histogram": {"bins": [], "counts": []},
            }

        arr = np.asarray(clean, dtype=float)
        c_min = float(np.min(arr))
        c_max = float(np.max(arr))
        c_mean = float(np.mean(arr))
        c_std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        c_med = float(np.median(arr))
        p25 = float(np.percentile(arr, 25))
        p75 = float(np.percentile(arr, 75))
        p95 = float(np.percentile(arr, 95))

        if c_min == c_max:
            bins = [c_min - 1.0, c_max + 1.0]
            counts = [len(clean)]
        else:
            counts_arr, bins_arr = np.histogram(arr, bins=num_bins)
            bins = [round(float(b), 4) for b in bins_arr]
            counts = [int(c) for c in counts_arr]

        return {
            "count": len(clean),
            "null_count": len(values) - len(clean),
            "null_rate": round((len(values) - len(clean)) / len(values), 4) if values else 0.0,
            "mean": round(c_mean, 4),
            "std": round(c_std, 4),
            "min": round(c_min, 4),
            "max": round(c_max, 4),
            "median": round(c_med, 4),
            "p25": round(p25, 4),
            "p75": round(p75, 4),
            "p95": round(p95, 4),
            "iqr": round(p75 - p25, 4),
            "histogram": {"bins": bins, "counts": counts},
        }
