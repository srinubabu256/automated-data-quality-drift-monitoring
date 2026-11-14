"""Tests for late-arriving events and historical date recomputation."""
from datetime import date
from decimal import Decimal
from app.processing.transaction_processor import TransactionProcessor
from app.models.database_models import DailyMetric, Transaction


def test_late_arriving_event_recomputes_historical_date(test_db):
    """Verify late-arriving event updates historical business date metrics correctly."""
    processor = TransactionProcessor(db=test_db)

    # Initial batch with events on 2026-11-10
    batch_today = [
        {
            "event_id": "evt_today_01",
            "transaction_id": "TXN_TODAY_1",
            "customer_id": "CUST_001",
            "product_id": "PROD_001",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T14:00:00Z",
        }
    ]
    processor.process_records(batch_today, source_name="batch_today")

    m_today = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 10)).first()
    assert m_today is not None
    assert m_today.total_transactions == 1
    assert m_today.total_amount == Decimal("100.00")

    # Now a late-arriving event arrives with timestamp on 2026-11-05 (5 days earlier)
    batch_late = [
        {
            "event_id": "evt_late_01",
            "transaction_id": "TXN_LATE_1",
            "customer_id": "CUST_002",
            "product_id": "PROD_002",
            "event_type": "NEW",
            "amount": "250.00",
            "currency": "USD",
            "event_timestamp": "2026-11-05T08:30:00Z",  # Historical date
        }
    ]
    res = processor.process_records(batch_late, source_name="batch_late")
    assert "2026-11-05" in res.affected_dates

    # Check that historical metric for 2026-11-05 now exists and has 250.00
    m_hist = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 5)).first()
    assert m_hist is not None
    assert m_hist.total_transactions == 1
    assert m_hist.total_amount == Decimal("250.00")
    assert m_hist.active_customers == 1
    assert m_hist.active_products == 1

    # Today's metric should remain untouched at 100.00
    m_today_refreshed = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 10)).first()
    assert m_today_refreshed.total_amount == Decimal("100.00")

