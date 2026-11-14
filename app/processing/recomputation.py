"""Historical Metric Recomputation Engine for updating daily business aggregates."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable, List, Optional, Set
from sqlalchemy import func, distinct, case
from sqlalchemy.orm import Session

from app.models.database_models import (
    Transaction,
    RawEvent,
    RejectedRecord,
    DailyMetric,
)


class RecomputationEngine:
    """Recomputes daily business metrics for affected dates deterministically."""

    @staticmethod
    def recompute_dates(
        db: Session,
        affected_dates: Iterable[date],
        run_id: Optional[str] = None
    ) -> List[DailyMetric]:
        """
        Recomputes daily metrics for each given business date.
        Updates or inserts DailyMetric rows idempotently.
        """
        updated_metrics: List[DailyMetric] = []
        now = datetime.now(timezone.utc)

        for target_date in sorted(set(affected_dates)):
            # 1. Active transaction aggregates for target date
            active_tx_query = db.query(
                func.count(Transaction.transaction_id).label("total_tx"),
                func.coalesce(func.sum(Transaction.current_amount), 0).label("total_amt"),
                func.count(distinct(Transaction.customer_id)).label("active_cust"),
                func.count(distinct(Transaction.product_id)).label("active_prod"),
                func.coalesce(func.avg(Transaction.current_amount), 0).label("avg_amt"),
                func.coalesce(func.min(Transaction.current_amount), 0).label("min_amt"),
                func.coalesce(func.max(Transaction.current_amount), 0).label("max_amt"),
            ).filter(
                func.date(Transaction.first_event_timestamp) == target_date,
                Transaction.is_reversed == False,
                Transaction.current_amount > 0
            ).first()

            total_tx = active_tx_query.total_tx or 0
            total_amt = Decimal(str(active_tx_query.total_amt or 0))
            active_cust = active_tx_query.active_cust or 0
            active_prod = active_tx_query.active_prod or 0
            avg_amt = Decimal(str(round(active_tx_query.avg_amt or 0, 2)))
            min_amt = Decimal(str(active_tx_query.min_amt or 0))
            max_amt = Decimal(str(active_tx_query.max_amt or 0))

            # 2. Raw events volume and duplicates for target date
            raw_stats = db.query(
                func.count(RawEvent.id).label("total_raw"),
                func.coalesce(func.sum(case((RawEvent.status == "DUPLICATE", 1), else_=0)), 0).label("dup_count"),
                func.max(RawEvent.event_timestamp).label("max_event_ts"),
                func.max(RawEvent.ingestion_timestamp).label("max_ingest_ts"),
            ).filter(
                func.date(RawEvent.event_timestamp) == target_date
            ).first()

            record_volume = raw_stats.total_raw or 0
            duplicate_count = int(raw_stats.dup_count or 0)
            max_event_ts = raw_stats.max_event_ts
            max_ingest_ts = raw_stats.max_ingest_ts

            # 3. Rejected records count for target date
            rejected_count = db.query(func.count(RejectedRecord.id)).filter(
                func.date(RejectedRecord.rejected_at) == target_date
            ).scalar() or 0

            # 4. Null rate & Freshness calculations
            total_activity = record_volume + rejected_count
            null_rate = float(rejected_count) / float(total_activity) if total_activity > 0 else 0.0

            event_freshness_sec = 0.0
            if max_event_ts:
                if max_event_ts.tzinfo is None:
                    max_event_ts = max_event_ts.replace(tzinfo=timezone.utc)
                event_freshness_sec = max(0.0, (now - max_event_ts).total_seconds())

            ingestion_freshness_sec = 0.0
            if max_ingest_ts:
                if max_ingest_ts.tzinfo is None:
                    max_ingest_ts = max_ingest_ts.replace(tzinfo=timezone.utc)
                ingestion_freshness_sec = max(0.0, (now - max_ingest_ts).total_seconds())

            # 5. Upsert into daily_metrics table
            metric_entry = db.query(DailyMetric).filter_by(
                metric_date=target_date,
                dimension_type="TOTAL",
                dimension_value="ALL"
            ).first()

            if not metric_entry:
                metric_entry = DailyMetric(
                    metric_date=target_date,
                    dimension_type="TOTAL",
                    dimension_value="ALL",
                    total_transactions=total_tx,
                    total_amount=total_amt,
                    active_customers=active_cust,
                    active_products=active_prod,
                    avg_amount=avg_amt,
                    min_amount=min_amt,
                    max_amount=max_amt,
                    null_rate=round(null_rate, 4),
                    record_volume=record_volume,
                    event_freshness_sec=round(event_freshness_sec, 2),
                    ingestion_freshness_sec=round(ingestion_freshness_sec, 2),
                    rejected_count=rejected_count,
                    duplicate_count=duplicate_count,
                    computed_at=now,
                    run_id=run_id,
                )
                db.add(metric_entry)
            else:
                metric_entry.total_transactions = total_tx
                metric_entry.total_amount = total_amt
                metric_entry.active_customers = active_cust
                metric_entry.active_products = active_prod
                metric_entry.avg_amount = avg_amt
                metric_entry.min_amount = min_amt
                metric_entry.max_amount = max_amt
                metric_entry.null_rate = round(null_rate, 4)
                metric_entry.record_volume = record_volume
                metric_entry.event_freshness_sec = round(event_freshness_sec, 2)
                metric_entry.ingestion_freshness_sec = round(ingestion_freshness_sec, 2)
                metric_entry.rejected_count = rejected_count
                metric_entry.duplicate_count = duplicate_count
                metric_entry.computed_at = now
                metric_entry.run_id = run_id

            updated_metrics.append(metric_entry)

        db.flush()
        return updated_metrics
