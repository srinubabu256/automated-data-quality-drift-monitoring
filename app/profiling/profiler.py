"""Data quality profiler generating statistical summaries and distributions."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.database_models import DataQualityProfile, ProcessingRun, RawEvent
from app.profiling.distribution import DistributionCalculator


class Profiler:
    """Computes and stores statistical data quality profiles for batches."""

    @classmethod
    def create_batch_profile(
        cls,
        db: Session,
        run_id: str,
        rows: List[Dict[str, Any]],
        accepted_items: List[Dict[str, Any]],
        rejected_items: List[Dict[str, Any]],
    ) -> DataQualityProfile:
        """
        Creates or updates a DataQualityProfile record for the run.
        """
        batch_volume = len(rows)
        null_rate = float(len(rejected_items)) / float(batch_volume) if batch_volume > 0 else 0.0

        # Extract amounts from accepted items
        amounts: List[float] = []
        latest_ts: Optional[datetime] = None

        for item in accepted_items:
            d = item.get("data", {})
            amt = d.get("amount")
            if amt is not None:
                try:
                    amounts.append(float(amt))
                except (ValueError, TypeError):
                    pass

            ts = d.get("event_timestamp")
            if ts:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts

        # Descriptive statistics
        summary = DistributionCalculator.calculate_numeric_summary(amounts)

        now = datetime.now(timezone.utc)
        freshness_sec = 0.0
        if latest_ts:
            freshness_sec = max(0.0, (now - latest_ts).total_seconds())

        profile = db.query(DataQualityProfile).filter_by(run_id=run_id).first()
        if not profile:
            profile = DataQualityProfile(
                run_id=run_id,
                batch_volume=batch_volume,
                null_rate=round(null_rate, 4),
                mean_amount=summary["mean"],
                std_amount=summary["std"],
                min_amount=summary["min"],
                max_amount=summary["max"],
                median_amount=summary["median"],
                p95_amount=summary["p95"],
                event_freshness_sec=round(freshness_sec, 2),
                created_at=now,
            )
            db.add(profile)
        else:
            profile.batch_volume = batch_volume
            profile.null_rate = round(null_rate, 4)
            profile.mean_amount = summary["mean"]
            profile.std_amount = summary["std"]
            profile.min_amount = summary["min"]
            profile.max_amount = summary["max"]
            profile.median_amount = summary["median"]
            profile.p95_amount = summary["p95"]
            profile.event_freshness_sec = round(freshness_sec, 2)

        db.commit()
        db.refresh(profile)
        return profile

    @classmethod
    def profile_run(
        cls,
        db: Session,
        run_id: str,
        amounts: Optional[List[float]] = None
    ) -> DataQualityProfile:
        """Alias for profiling when only run_id is passed."""
        run = db.query(ProcessingRun).filter_by(run_id=run_id).first()
        if not run:
            raise ValueError(f"ProcessingRun {run_id} not found.")

        if amounts is None:
            raw_amounts = (
                db.query(RawEvent.amount)
                .filter(RawEvent.run_id == run_id, RawEvent.amount.isnot(None))
                .all()
            )
            amounts = [float(r[0]) for r in raw_amounts if r[0] is not None]

        summary = DistributionCalculator.calculate_numeric_summary(amounts)
        total_items = run.input_count
        null_rate = float(run.rejected_count) / float(total_items) if total_items > 0 else 0.0

        now = datetime.now(timezone.utc)
        latest_event = (
            db.query(RawEvent.event_timestamp)
            .filter_by(run_id=run_id)
            .order_by(RawEvent.event_timestamp.desc())
            .first()
        )
        freshness_sec = 0.0
        if latest_event and latest_event[0]:
            ts = latest_event[0]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            freshness_sec = max(0.0, (now - ts).total_seconds())

        profile = db.query(DataQualityProfile).filter_by(run_id=run_id).first()
        if not profile:
            profile = DataQualityProfile(
                run_id=run_id,
                batch_volume=run.input_count,
                null_rate=round(null_rate, 4),
                mean_amount=summary["mean"],
                std_amount=summary["std"],
                min_amount=summary["min"],
                max_amount=summary["max"],
                median_amount=summary["median"],
                p95_amount=summary["p95"],
                event_freshness_sec=round(freshness_sec, 2),
                created_at=now,
            )
            db.add(profile)
        else:
            profile.batch_volume = run.input_count
            profile.null_rate = round(null_rate, 4)
            profile.mean_amount = summary["mean"]
            profile.std_amount = summary["std"]
            profile.min_amount = summary["min"]
            profile.max_amount = summary["max"]
            profile.median_amount = summary["median"]
            profile.p95_amount = summary["p95"]
            profile.event_freshness_sec = round(freshness_sec, 2)

        db.commit()
        db.refresh(profile)
        return profile


# Backward-compatible alias
BatchProfiler = Profiler


class ColumnProfiler:
    """Computes individual column-level profiling metrics, distributions, and histogram buckets."""

    NUMERIC_COLUMNS = {"amount"}
    CATEGORICAL_COLUMNS = {"event_type", "currency", "source_system"}
    ID_COLUMNS = {"event_id", "transaction_id", "customer_id", "product_id"}
    TIMESTAMP_COLUMNS = {"event_timestamp"}

    @classmethod
    def profile_columns(
        cls,
        records: List[Dict[str, Any]],
        run_id: str = "RUN_ADHOC",
        source_file: str = "UNKNOWN",
        baseline_version: str = "v1.0"
    ) -> Dict[str, Any]:
        """
        Profiles every column in the dataset individually.
        Returns comprehensive column profiling dictionary.
        """
        total_records = len(records)
        now = datetime.now(timezone.utc).isoformat()

        if not records:
            return {
                "run_id": run_id,
                "source_file": source_file,
                "baseline_version": baseline_version,
                "total_records": 0,
                "profiled_at": now,
                "columns": {}
            }

        all_cols = set()
        for r in records:
            all_cols.update(r.keys())

        col_profiles = {}
        for col in sorted(all_cols):
            values = [r.get(col) for r in records]
            non_null_vals = [v for v in values if v is not None and str(v).strip() != "" and str(v).lower() != "nan"]
            null_count = total_records - len(non_null_vals)
            null_pct = round((null_count / total_records) * 100.0, 2) if total_records > 0 else 0.0
            distinct_count = len(set(str(v) for v in non_null_vals))
            duplicate_count = max(0, len(non_null_vals) - distinct_count)

            if col in cls.NUMERIC_COLUMNS:
                col_type = "NUMERIC"
            elif col in cls.TIMESTAMP_COLUMNS:
                col_type = "TIMESTAMP"
            elif col in cls.CATEGORICAL_COLUMNS:
                col_type = "CATEGORICAL"
            else:
                col_type = "STRING"

            profile = {
                "column_name": col,
                "data_type": col_type,
                "total_count": total_records,
                "null_count": null_count,
                "null_pct": null_pct,
                "distinct_count": distinct_count,
                "duplicate_count": duplicate_count,
            }

            if col_type == "NUMERIC" or col == "amount":
                num_vals = []
                for v in non_null_vals:
                    try:
                        num_vals.append(float(v))
                    except (ValueError, TypeError):
                        pass

                if num_vals:
                    num_summary = DistributionCalculator.calculate_numeric_summary(num_vals)
                    profile["min"] = num_summary["min"]
                    profile["max"] = num_summary["max"]
                    profile["mean"] = num_summary["mean"]
                    profile["median"] = num_summary["median"]
                    profile["std"] = num_summary["std"]

                    min_v = num_summary["min"]
                    max_v = num_summary["max"]
                    if max_v > min_v:
                        bin_width = (max_v - min_v) / 5.0
                        buckets = []
                        for i in range(5):
                            b_start = round(min_v + i * bin_width, 2)
                            b_end = round(min_v + (i + 1) * bin_width, 2)
                            b_count = sum(1 for x in num_vals if (b_start <= x <= b_end if i == 4 else b_start <= x < b_end))
                            buckets.append({"bucket": f"[{b_start}, {b_end})", "count": b_count})
                        profile["histogram_buckets"] = buckets
                    else:
                        profile["histogram_buckets"] = [{"bucket": f"[{min_v}, {max_v}]", "count": len(num_vals)}]
                else:
                    profile["min"] = 0.0
                    profile["max"] = 0.0
                    profile["mean"] = 0.0
                    profile["median"] = 0.0
                    profile["std"] = 0.0
                    profile["histogram_buckets"] = []

            if col_type in ("CATEGORICAL", "STRING") or col in ("event_type", "currency", "source_system"):
                freq = {}
                for v in non_null_vals:
                    k = str(v).strip()
                    freq[k] = freq.get(k, 0) + 1
                sorted_freq = dict(sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10])
                profile["frequency_distribution"] = sorted_freq

            col_profiles[col] = profile

        return {
            "run_id": run_id,
            "source_file": source_file,
            "baseline_version": baseline_version,
            "total_records": total_records,
            "profiled_at": now,
            "columns": col_profiles
        }

    @classmethod
    def compare_column_baselines(
        cls,
        baseline_profile: Dict[str, Any],
        current_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare current column profile against baseline column profile.
        Detects volume, null-rate, numerical distribution, categorical distribution, and schema drift.
        """
        b_cols = baseline_profile.get("columns", {})
        c_cols = current_profile.get("columns", {})

        b_vol = baseline_profile.get("total_records", 0)
        c_vol = current_profile.get("total_records", 0)
        vol_diff = c_vol - b_vol
        vol_pct = (vol_diff / b_vol * 100.0) if b_vol > 0 else 0.0

        missing_columns = sorted(list(set(b_cols.keys()) - set(c_cols.keys())))
        new_columns = sorted(list(set(c_cols.keys()) - set(b_cols.keys())))
        schema_drift = len(missing_columns) > 0 or len(new_columns) > 0

        comparisons = {
            "baseline_version": baseline_profile.get("baseline_version", "v1.0"),
            "run_id": current_profile.get("run_id"),
            "volume_comparison": {
                "baseline_volume": b_vol,
                "current_volume": c_vol,
                "diff": vol_diff,
                "pct_change": round(vol_pct, 2)
            },
            "schema_changes": {
                "schema_drift_detected": schema_drift,
                "missing_columns": missing_columns,
                "new_columns": new_columns,
            },
            "column_comparisons": {}
        }

        common_cols = sorted(list(set(b_cols.keys()).intersection(set(c_cols.keys()))))
        for col in common_cols:
            b_info = b_cols[col]
            c_info = c_cols[col]

            col_comp = {
                "null_pct_diff": round(c_info.get("null_pct", 0.0) - b_info.get("null_pct", 0.0), 2),
                "distinct_count_diff": c_info.get("distinct_count", 0) - b_info.get("distinct_count", 0),
            }

            if "mean" in b_info and "mean" in c_info:
                b_mean = b_info["mean"]
                c_mean = c_info["mean"]
                mean_diff = c_mean - b_mean
                mean_pct = (mean_diff / b_mean * 100.0) if b_mean > 0 else 0.0
                col_comp["numerical_drift"] = {
                    "baseline_mean": b_mean,
                    "current_mean": c_mean,
                    "diff": round(mean_diff, 2),
                    "pct_change": round(mean_pct, 2),
                }

            if "frequency_distribution" in b_info and "frequency_distribution" in c_info:
                b_freq = b_info["frequency_distribution"]
                c_freq = c_info["frequency_distribution"]
                cat_diffs = {}
                for k in sorted(set(b_freq.keys()).union(set(c_freq.keys()))):
                    cat_diffs[k] = c_freq.get(k, 0) - b_freq.get(k, 0)
                col_comp["categorical_distribution_shift"] = cat_diffs

            comparisons["column_comparisons"][col] = col_comp

        return comparisons
