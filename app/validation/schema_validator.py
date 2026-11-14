"""Schema and type validation engine for raw transaction events."""
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple
from dateutil import parser as date_parser

from app.models.enums import EventType


class SchemaValidator:
    """Validates structural constraints, data types, nulls, and formatting."""

    REQUIRED_FIELDS = [
        "event_id",
        "transaction_id",
        "customer_id",
        "product_id",
        "event_type",
        "amount",
        "event_timestamp"
    ]

    VALID_EVENT_TYPES = {EventType.NEW.value, EventType.UPDATE.value, EventType.REVERSAL.value}

    SUPPORTED_CURRENCIES = {
        "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR", "CHF", "CNY", "SGD", "NZD", "HKD", "SEK"
    }

    @classmethod
    def validate_record(cls, row: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """
        Validates a single raw row dictionary.
        Returns:
            (is_valid, rejection_reason, rejection_code, validated_data)
        """
        # 1. Required columns presence and non-empty check
        for field in cls.REQUIRED_FIELDS:
            val = row.get(field)
            if val is None or str(val).strip() == "":
                return False, f"Missing or null required field: '{field}'", "MISSING_REQUIRED_FIELD", None

        # Clean string values
        event_id = str(row["event_id"]).strip()
        transaction_id = str(row["transaction_id"]).strip()
        customer_id = str(row["customer_id"]).strip()
        product_id = str(row["product_id"]).strip()
        event_type = str(row["event_type"]).strip().upper()
        amount_raw = str(row["amount"]).strip()
        
        # Currency check: default to USD if omitted, but if present must be in ISO 4217 allowlist
        if "currency" in row:
            curr_val = row["currency"]
            if curr_val is None or str(curr_val).strip() == "":
                return False, "Currency field cannot be empty", "MISSING_REQUIRED_FIELD", None
            currency = str(curr_val).strip()
            if not re.match(r"^[A-Z]{3}$", currency):
                return False, f"Invalid currency code '{currency}'. Must be 3 uppercase letters.", "INVALID_CURRENCY", None
            if currency not in cls.SUPPORTED_CURRENCIES:
                return False, f"Unsupported currency code '{currency}'. Must be one of: {sorted(cls.SUPPORTED_CURRENCIES)}", "UNSUPPORTED_CURRENCY", None
        else:
            currency = "USD"
        
        timestamp_raw = str(row["event_timestamp"]).strip()
        source_system = str(row.get("source_system", "UNKNOWN")).strip()

        # String length boundary checks (DB column width safety)
        if len(event_id) > 64 or len(transaction_id) > 64 or len(customer_id) > 64 or len(product_id) > 64:
            return False, "Identifier exceeds maximum allowable field length (64 characters)", "FIELD_VALUE_TOO_LONG", None

        # 2. Event type check
        if event_type not in cls.VALID_EVENT_TYPES:
            return False, f"Invalid event_type '{event_type}'. Must be NEW, UPDATE, or REVERSAL", "INVALID_EVENT_TYPE", None

        # 3. Numeric Amount check (must be positive decimal within bounds)
        try:
            amt = Decimal(amount_raw)
            if amt <= Decimal("0.00"):
                return False, f"Invalid amount '{amount_raw}'. Amount must be strictly greater than 0.00", "INVALID_AMOUNT_VALUE", None
            if amt > Decimal("999999999999.99"):
                return False, f"Amount '{amount_raw}' exceeds maximum allowable limit of $999,999,999,999.99", "AMOUNT_EXCEEDS_MAX_LIMIT", None
            # Round to 2 decimal places
            amt = amt.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return False, f"Non-numeric amount value: '{amount_raw}'", "MALFORMED_AMOUNT_TYPE", None

        # 4. Currency check
        if not re.match(r"^[A-Z]{3}$", currency):
            return False, f"Invalid currency code '{currency}'. Must be 3 uppercase letters.", "INVALID_CURRENCY", None

        # 5. Timestamp validation
        try:
            # Parse timestamp supporting ISO-8601 UTC formats
            dt = date_parser.isoparse(timestamp_raw)
            # Ensure timezone awareness; default naive timestamps to UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)

            # Sanity check year range (e.g. 2000 to 2100)
            if dt.year < 2000 or dt.year > 2100:
                return False, f"Timestamp year out of allowable bounds: {dt.year}", "OUT_OF_BOUNDS_TIMESTAMP", None
        except Exception as e:
            return False, f"Malformed event_timestamp '{timestamp_raw}': {e}", "MALFORMED_TIMESTAMP", None

        validated_data = {
            "event_id": event_id,
            "transaction_id": transaction_id,
            "customer_id": customer_id,
            "product_id": product_id,
            "event_type": event_type,
            "amount": amt,
            "currency": currency,
            "event_timestamp": dt,
            "source_system": source_system,
        }
        return True, None, None, validated_data

