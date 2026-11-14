"""Handler for REVERSAL transaction events, double-reversal prevention, and history tracking."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.database_models import Transaction, TransactionHistory


class ReversalHandler:
    """Applies transaction reversals safely and idempotently."""

    @staticmethod
    def process_reversal(
        db: Session,
        event_data: Dict[str, Any],
        run_id: str,
        tx_cache: Optional[Dict[str, Transaction]] = None
    ) -> Tuple[bool, Optional[str], Optional[Transaction]]:
        """
        Processes a REVERSAL event.
        Returns:
            (success, message, transaction_instance)
        """
        tx_id = event_data["transaction_id"]
        event_id = event_data["event_id"]
        event_ts = event_data["event_timestamp"]
        cust_id = event_data["customer_id"]
        prod_id = event_data["product_id"]
        currency = event_data.get("currency", "USD")

        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)

        existing_tx = tx_cache.get(tx_id) if tx_cache is not None else None
        if not existing_tx:
            existing_tx = db.query(Transaction).filter_by(transaction_id=tx_id).first()
            if existing_tx and tx_cache is not None:
                tx_cache[tx_id] = existing_tx

        # Case 1: Transaction doesn't exist yet (out-of-order REVERSAL before NEW)
        if not existing_tx:
            tx = Transaction(
                transaction_id=tx_id,
                customer_id=cust_id,
                product_id=prod_id,
                current_amount=Decimal("0.00"),
                currency=currency,
                status="REVERSED",
                is_reversed=True,
                version=1,
                first_event_timestamp=event_ts,
                latest_event_timestamp=event_ts,
                latest_event_id=event_id,
                last_run_id=run_id,
            )
            db.add(tx)
            if tx_cache is not None:
                tx_cache[tx_id] = tx

            hist = TransactionHistory(
                transaction_id=tx_id,
                event_id=event_id,
                event_type="REVERSAL",
                previous_amount=Decimal("0.00"),
                new_amount=Decimal("0.00"),
                event_timestamp=event_ts,
                applied_at=datetime.now(timezone.utc),
                run_id=run_id,
            )
            db.add(hist)
            return True, "Created reversed transaction from out-of-order REVERSAL", tx

        # Case 2: Double Reversal Prevention
        if existing_tx.is_reversed:
            hist = TransactionHistory(
                transaction_id=tx_id,
                event_id=event_id,
                event_type="REVERSAL_DUPLICATE_IGNORED",
                previous_amount=existing_tx.current_amount,
                new_amount=existing_tx.current_amount,
                event_timestamp=event_ts,
                applied_at=datetime.now(timezone.utc),
                run_id=run_id,
            )
            db.add(hist)
            return True, f"Transaction {tx_id} already reversed; duplicate reversal ignored", existing_tx

        # Case 3: Normal Reversal
        old_amt = existing_tx.current_amount
        existing_tx.status = "REVERSED"
        existing_tx.is_reversed = True
        existing_tx.current_amount = Decimal("0.00")
        existing_tx.latest_event_timestamp = max(
            existing_tx.latest_event_timestamp.replace(tzinfo=timezone.utc)
            if existing_tx.latest_event_timestamp.tzinfo is None
            else existing_tx.latest_event_timestamp,
            event_ts
        )
        existing_tx.latest_event_id = event_id
        existing_tx.version += 1
        existing_tx.last_run_id = run_id
        existing_tx.updated_at = datetime.now(timezone.utc)

        hist = TransactionHistory(
            transaction_id=tx_id,
            event_id=event_id,
            event_type="REVERSAL",
            previous_amount=old_amt,
            new_amount=Decimal("0.00"),
            event_timestamp=event_ts,
            applied_at=datetime.now(timezone.utc),
            run_id=run_id,
        )
        db.add(hist)
        return True, "Reversed transaction successfully", existing_tx
