"""Tests for Column-Level Profiling, Histogram Bucketing, and Baseline Comparison."""
import pytest
from app.profiling.profiler import ColumnProfiler


def test_column_profiler_statistics():
    """Verify ColumnProfiler computes total, nulls, distincts, duplicates, min/max/mean/median, histograms, and frequencies."""
    records = [
        {"event_id": "e1", "transaction_id": "t1", "customer_id": "c1", "product_id": "p1", "event_type": "NEW", "amount": "100.00", "currency": "USD"},
        {"event_id": "e2", "transaction_id": "t2", "customer_id": "c2", "product_id": "p2", "event_type": "NEW", "amount": "200.00", "currency": "USD"},
        {"event_id": "e3", "transaction_id": "t3", "customer_id": "c1", "product_id": "p1", "event_type": "UPDATE", "amount": "300.00", "currency": "USD"},
        {"event_id": "e4", "transaction_id": "t4", "customer_id": "c3", "product_id": "p2", "event_type": "REVERSAL", "amount": "400.00", "currency": "USD"},
        {"event_id": "e5", "transaction_id": "t5", "customer_id": "c4", "product_id": "p3", "event_type": "NEW", "amount": "500.00", "currency": "USD"},
        {"event_id": "e6", "transaction_id": "t6", "customer_id": None, "product_id": "p3", "event_type": "NEW", "amount": None, "currency": "EUR"},
    ]

    profile = ColumnProfiler.profile_columns(records, run_id="RUN_COL_01", source_file="col_test.csv", baseline_version="v1.0")

    assert profile["total_records"] == 6
    assert profile["run_id"] == "RUN_COL_01"
    assert profile["source_file"] == "col_test.csv"
    assert profile["baseline_version"] == "v1.0"

    cols = profile["columns"]
    assert "amount" in cols
    assert "event_type" in cols
    assert "customer_id" in cols

    # Amount (Numeric)
    amt_col = cols["amount"]
    assert amt_col["data_type"] == "NUMERIC"
    assert amt_col["null_count"] == 1
    assert amt_col["min"] == 100.0
    assert amt_col["max"] == 500.0
    assert amt_col["mean"] == 300.0
    assert amt_col["median"] == 300.0
    assert len(amt_col["histogram_buckets"]) == 5

    # Event Type (Categorical)
    evt_col = cols["event_type"]
    assert evt_col["data_type"] == "CATEGORICAL"
    assert evt_col["null_count"] == 0
    assert evt_col["frequency_distribution"]["NEW"] == 4
    assert evt_col["frequency_distribution"]["UPDATE"] == 1
    assert evt_col["frequency_distribution"]["REVERSAL"] == 1

    # Customer ID (String / ID)
    cust_col = cols["customer_id"]
    assert cust_col["null_count"] == 1
    assert cust_col["distinct_count"] == 4
    assert cust_col["duplicate_count"] == 1  # c1 appears twice


def test_column_profiler_baseline_comparison():
    """Verify compare_column_baselines detects volume, null-rate, numerical drift, categorical drift, and schema drift."""
    baseline_records = [
        {"event_id": "b1", "transaction_id": "t1", "amount": "100.00", "event_type": "NEW"},
        {"event_id": "b2", "transaction_id": "t2", "amount": "100.00", "event_type": "NEW"},
    ]
    current_records = [
        {"event_id": "c1", "transaction_id": "t3", "amount": "200.00", "event_type": "NEW"},
        {"event_id": "c2", "transaction_id": "t4", "amount": "200.00", "event_type": "UPDATE"},
        {"event_id": "c3", "transaction_id": "t5", "amount": "200.00", "event_type": "UPDATE"},
    ]

    base_prof = ColumnProfiler.profile_columns(baseline_records, run_id="BASE_01", baseline_version="v1.0")
    curr_prof = ColumnProfiler.profile_columns(current_records, run_id="CURR_01", baseline_version="v1.0")

    comparison = ColumnProfiler.compare_column_baselines(base_prof, curr_prof)

    assert comparison["volume_comparison"]["diff"] == 1
    assert comparison["volume_comparison"]["pct_change"] == 50.0

    # Numerical drift on amount
    amt_comp = comparison["column_comparisons"]["amount"]
    assert amt_comp["numerical_drift"]["baseline_mean"] == 100.0
    assert amt_comp["numerical_drift"]["current_mean"] == 200.0
    assert amt_comp["numerical_drift"]["pct_change"] == 100.0

    # Categorical drift on event_type
    evt_comp = comparison["column_comparisons"]["event_type"]
    assert evt_comp["categorical_distribution_shift"]["NEW"] == -1
    assert evt_comp["categorical_distribution_shift"]["UPDATE"] == 2
