"""Datetime profiling and temporal freshness latency calculations."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from dateutil import parser


class DatetimeProfiler:
    """Computes time bounds, event-time span, and freshness latency for temporal features."""

    @staticmethod
    def calculate_summary(values: List[Any]) -> Dict[str, Any]:
        total = len(values)
        parsed_dates: List[datetime] = []
        null_count = 0

        for v in values:
            if v is None:
                null_count += 1
                continue
            if isinstance(v, datetime):
                dt = v
            else:
                try:
                    dt = parser.isoparse(str(v).strip())
                except Exception:
                    null_count += 1
                    continue

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parsed_dates.append(dt)

        if not parsed_dates:
            return {
                "total_count": total,
                "null_count": null_count,
                "null_rate": round(null_count / total, 4) if total > 0 else 0.0,
                "min_timestamp": None,
                "max_timestamp": None,
                "span_days": 0.0,
                "freshness_sec": 0.0,
            }

        min_ts = min(parsed_dates)
        max_ts = max(parsed_dates)
        now = datetime.now(timezone.utc)
        freshness_sec = max(0.0, (now - max_ts).total_seconds())
        span_days = (max_ts - min_ts).total_seconds() / 86400.0

        return {
            "total_count": total,
            "null_count": null_count,
            "null_rate": round(null_count / total, 4) if total > 0 else 0.0,
            "min_timestamp": min_ts.isoformat(),
            "max_timestamp": max_ts.isoformat(),
            "span_days": round(span_days, 2),
            "freshness_sec": round(freshness_sec, 2),
        }
