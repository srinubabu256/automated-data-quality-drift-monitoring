"""Unit tests for granular column profilers (Numeric, Categorical, Datetime)."""
import pytest
from app.profiling.numeric import NumericProfiler
from app.profiling.categorical import CategoricalProfiler
from app.profiling.datetime import DatetimeProfiler


def test_numeric_profiler_standard_and_empty():
    """Verify NumericProfiler computes summary metrics and handles empty lists."""
    values = [10.0, 20.0, 30.0, 40.0, 50.0, None]
    summary = NumericProfiler.calculate_summary(values, num_bins=5)
    assert summary["count"] == 5
    assert summary["null_count"] == 1
    assert summary["mean"] == 30.0
    assert summary["median"] == 30.0
    assert summary["min"] == 10.0
    assert summary["max"] == 50.0
    assert len(summary["histogram"]["bins"]) > 0

    # Empty list
    empty_summary = NumericProfiler.calculate_summary([])
    assert empty_summary["count"] == 0
    assert empty_summary["null_rate"] == 0.0

    # Uniform list
    uniform_summary = NumericProfiler.calculate_summary([100.0, 100.0, 100.0])
    assert uniform_summary["min"] == 100.0
    assert uniform_summary["max"] == 100.0


def test_categorical_profiler_standard_and_nulls():
    """Verify CategoricalProfiler counts distinct categories, mode, and frequencies."""
    values = ["USD", "EUR", "USD", "GBP", "USD", "EUR", None, ""]
    summary = CategoricalProfiler.calculate_summary(values, top_k=2)
    assert summary["total_count"] == 8
    assert summary["null_count"] == 2
    assert summary["distinct_count"] == 3
    assert summary["mode"] == "USD"
    assert len(summary["top_categories"]) == 2
    assert summary["frequencies"]["USD"] == 3


def test_datetime_profiler_standard_and_empty():
    """Verify DatetimeProfiler parses ISO strings and computes span and freshness."""
    values = [
        "2026-11-10T10:00:00Z",
        "2026-11-12T10:00:00Z",
        None,
        "invalid_date",
    ]
    summary = DatetimeProfiler.calculate_summary(values)
    assert summary["total_count"] == 4
    assert summary["null_count"] == 2
    assert summary["min_timestamp"] is not None
    assert summary["max_timestamp"] is not None
    assert summary["span_days"] == pytest.approx(2.0, rel=1e-2)
    assert summary["freshness_sec"] >= 0.0

    # Empty
    empty_summary = DatetimeProfiler.calculate_summary([])
    assert empty_summary["total_count"] == 0
    assert empty_summary["min_timestamp"] is None
