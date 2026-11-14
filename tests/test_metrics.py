"""Tests for daily business metrics calculation and historical recomputation."""
from datetime import date
from decimal import Decimal
from app.processing.transaction_processor import TransactionProcessor
from app.models.database_models import DailyMetric


def test_daily_metrics_aggregates(test_db):
    """Verify daily metrics computation: sums, averages, active counts, min, max."""
    processor = TransactionProcessor(db=test_db)
    records = [
        {
            "event_id": "evt_m_1",
            "transaction_id": "TXN_M_1",
            "customer_id": "CUST_A",
            "product_id": "PROD_X",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T09:00:00Z",
        },
        {
            "event_id": "evt_m_2",
            "transaction_id": "TXN_M_2",
            "customer_id": "CUST_B",
            "product_id": "PROD_Y",
            "event_type": "NEW",
            "amount": "200.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T10:00:00Z",
        },
        {
            "event_id": "evt_m_3",
            "transaction_id": "TXN_M_3",
            "customer_id": "CUST_A",  # Repeat customer
            "product_id": "PROD_X",  # Repeat product
            "event_type": "NEW",
            "amount": "300.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T11:00:00Z",
        }
    ]
    processor.process_records(records, source_name="metrics_test")

    m = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 10)).first()
    assert m is not None
    assert m.total_transactions == 3
    assert m.total_amount == Decimal("600.00")
    assert m.active_customers == 2  # CUST_A and CUST_B
    assert m.active_products == 2   # PROD_X and PROD_Y
    assert m.avg_amount == Decimal("200.00")
    assert m.min_amount == Decimal("100.00")
    assert m.max_amount == Decimal("300.00")


def test_historical_recomputation_on_update(test_db):
    """Verify daily metrics reflect updated amounts after UPDATE event."""
    processor = TransactionProcessor(db=test_db)
    initial_records = [
        {
            "event_id": "evt_h_1",
            "transaction_id": "TXN_H_1",
            "customer_id": "CUST_1",
            "product_id": "PROD_1",
            "event_type": "NEW",
            "amount": "100.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T09:00:00Z",
        }
    ]
    processor.process_records(initial_records, source_name="h1")

    # Verify initial metric
    m1 = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 10)).first()
    assert m1.total_amount == Decimal("100.00")

    # Update amount from 100.00 to 450.00
    update_records = [
        {
            "event_id": "evt_h_2",
            "transaction_id": "TXN_H_1",
            "customer_id": "CUST_1",
            "product_id": "PROD_1",
            "event_type": "UPDATE",
            "amount": "450.00",
            "currency": "USD",
            "event_timestamp": "2026-11-10T14:00:00Z",
        }
    ]
    processor.process_records(update_records, source_name="h2")

    test_db.expire_all()
    m2 = test_db.query(DailyMetric).filter_by(metric_date=date(2026, 11, 10)).first()
    assert m2.total_transactions == 1
    assert m2.total_amount == Decimal("450.00")
    assert m2.avg_amount == Decimal("450.00")

