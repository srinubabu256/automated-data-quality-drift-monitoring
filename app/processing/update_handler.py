"""Handler for UPDATE transaction events, conflict resolution, and history tracking."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from sqlalchemy.orm import Session

from app.models.database_models import Transaction, TransactionHistory


class UpdateHandler:
    """Applies transaction updates with deterministic out-of-order protection."""

    @staticmethod
    def process_update(
        db: Session,
        event_data: Dict[str, Any],
        run_id: str,
        tx_cache: Optional[Dict[str, Transaction]] = None
    ) -> Tuple[bool, Optional[str], Optional[Transaction]]:
        """
        Processes an UPDATE event.
        Returns:
            (success, message, transaction_instance)
        """
        tx_id = event_data["transaction_id"]
        event_id = event_data["event_id"]
        event_ts = event_data["event_timestamp"]
        new_amt = Decimal(str(event_data["amount"]))
        cust_id = event_data["customer_id"]
        prod_id = event_data["product_id"]
        currency = event_data.get("currency", "USD")

        # Make sure event_ts is timezone-aware
        if event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)

        existing_tx = tx_cache.get(tx_id) if tx_cache is not None else None
        if not existing_tx:
            existing_tx = db.query(Transaction).filter_by(transaction_id=tx_id).first()
            if existing_tx and tx_cache is not None:
                tx_cache[tx_id] = existing_tx

        # Case 1: Transaction doesn't exist yet (out-of-order: UPDATE arrived before NEW)
        if not existing_tx:
            tx = Transaction(
                transaction_id=tx_id,
                customer_id=cust_id,
                product_id=prod_id,
                current_amount=new_amt,
                currency=currency,
                status="ACTIVE",
                is_reversed=False,
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
                event_type="UPDATE",
                previous_amount=Decimal("0.00"),
                new_amount=new_amt,
                event_timestamp=event_ts,
                applied_at=datetime.now(timezone.utc),
                run_id=run_id,
            )
            db.add(hist)
            return True, "Created transaction from out-of-order UPDATE", tx

        # Case 2: Transaction is already REVERSED
        if existing_tx.is_reversed:
            hist = TransactionHistory(
                transaction_id=tx_id,
                event_id=event_id,
                event_type="UPDATE_IGNORED_REVERSED",
                previous_amount=existing_tx.current_amount,
                new_amount=new_amt,
                event_timestamp=event_ts,
                applied_at=datetime.now(timezone.utc),
                run_id=run_id,
            )
            db.add(hist)
            return False, f"Cannot update reversed transaction {tx_id}", existing_tx

        # Case 3: Out-of-order event check (event is older than latest applied state)
        latest_ts = existing_tx.latest_event_timestamp
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=timezone.utc)

        if event_ts < latest_ts:
            # Deterministic policy: older event does NOT overwrite newer valid state
            hist = TransactionHistory(
                transaction_id=tx_id,
                event_id=event_id,
                event_type="UPDATE_SUPERSEDED",
                previous_amount=existing_tx.current_amount,
                new_amount=new_amt,
                event_timestamp=event_ts,
                applied_at=datetime.now(timezone.utc),
                run_id=run_id,
            )
            db.add(hist)
            return True, "Recorded superseded update; current state preserved", existing_tx

        # Case 4: Normal sequential update
        old_amt = existing_tx.current_amount
        existing_tx.current_amount = new_amt
        existing_tx.latest_event_timestamp = event_ts
        existing_tx.latest_event_id = event_id
        existing_tx.version += 1
        existing_tx.last_run_id = run_id
        existing_tx.updated_at = datetime.now(timezone.utc)

        hist = TransactionHistory(
            transaction_id=tx_id,
            event_id=event_id,
            event_type="UPDATE",
            previous_amount=old_amt,
            new_amount=new_amt,
            event_timestamp=event_ts,
            applied_at=datetime.now(timezone.utc),
            run_id=run_id,
        )
        db.add(hist)
        return True, "Updated transaction successfully", existing_tx
