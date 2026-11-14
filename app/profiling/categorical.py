"""Categorical profiling and discrete frequency distributions."""
from typing import Any, Dict, List


class CategoricalProfiler:
    """Computes distinct counts, frequencies, mode, and top values for categorical features."""

    @staticmethod
    def calculate_summary(values: List[Any], top_k: int = 10) -> Dict[str, Any]:
        total = len(values)
        frequencies: Dict[str, int] = {}
        null_count = 0

        for v in values:
            if v is None or str(v).strip() == "" or str(v).lower() == "nan":
                null_count += 1
            else:
                key = str(v).strip()
                frequencies[key] = frequencies.get(key, 0) + 1

        non_null_count = total - null_count
        sorted_items = sorted(frequencies.items(), key=lambda x: x[1], reverse=True)
        top_categories = sorted_items[:top_k]
        mode = top_categories[0][0] if top_categories else None

        proportions = {}
        if non_null_count > 0:
            for k, count in top_categories:
                proportions[k] = round(count / non_null_count, 4)

        return {
            "total_count": total,
            "non_null_count": non_null_count,
            "null_count": null_count,
            "null_rate": round(null_count / total, 4) if total > 0 else 0.0,
            "distinct_count": len(frequencies),
            "mode": mode,
            "top_categories": [
                {"value": k, "count": cnt, "percentage": round((cnt / total) * 100.0, 2) if total > 0 else 0.0}
                for k, cnt in top_categories
            ],
            "frequencies": {k: cnt for k, cnt in sorted_items},
            "proportions": proportions,
        }
