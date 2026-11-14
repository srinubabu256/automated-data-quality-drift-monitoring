"""Business integrity validator for customer/product reference keys and duplicate detection."""
import re
from typing import Any, Dict, Optional, Set, Tuple
from sqlalchemy.orm import Session
from app.models.database_models import RawEvent


# Reference identifier pattern: alphanumeric with underscores and hyphens only
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")


class BusinessValidator:
    """Validates business reference integrity and duplicate event IDs."""

    @classmethod
    def validate_reference_keys(cls, data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates customer_id, product_id, and transaction_id format.
        """
        cust_id = data.get("customer_id", "")
        prod_id = data.get("product_id", "")
        tx_id = data.get("transaction_id", "")

        if not IDENTIFIER_PATTERN.match(cust_id) or "UNKNOWN" in cust_id or "INV" in cust_id and "@" in cust_id:
            return False, f"Invalid customer reference key format: '{cust_id}'", "INVALID_CUSTOMER_KEY"

        if not IDENTIFIER_PATTERN.match(prod_id) or prod_id.upper() in {"NULL", "NONE"}:
            return False, f"Invalid product reference key format: '{prod_id}'", "INVALID_PRODUCT_KEY"

        if not IDENTIFIER_PATTERN.match(tx_id):
            return False, f"Invalid transaction ID format: '{tx_id}'", "INVALID_TRANSACTION_KEY"

        return True, None, None

    @classmethod
    def check_duplicate_event(
        cls,
        event_id: str,
        seen_in_batch: Set[str],
        db: Session,
        preloaded_db_events: Optional[Set[str]] = None
    ) -> bool:
        """
        Check if event_id is duplicated within current batch or already exists in database.
        """
        # Check in current batch
        if event_id in seen_in_batch:
            return True

        # Check in preloaded cache if available
        if preloaded_db_events is not None and event_id in preloaded_db_events:
            return True

        # Query database if cache not provided
        if preloaded_db_events is None:
            existing = db.query(RawEvent.id).filter_by(event_id=event_id).first()
            if existing is not None:
                return True

        return False

