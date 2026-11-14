"""Edge-case tests for schema boundaries, extreme amounts, unicode, and string limits."""
from decimal import Decimal
from app.validation.schema_validator import SchemaValidator
from app.validation.business_validator import BusinessValidator


def test_schema_maximum_amount_boundary():
    """Verify amount exceeding maximum supported boundary is rejected."""
    row = {
        "event_id": "evt_huge_1",
        "transaction_id": "TXN_HUGE_1",
        "customer_id": "CUST_001",
        "product_id": "PROD_001",
        "event_type": "NEW",
        "amount": "1000000000000.00",  # 1 Trillion exceeds 999,999,999,999.99
        "currency": "USD",
        "event_timestamp": "2026-11-10T12:00:00Z",
    }
    is_valid, reason, code, _ = SchemaValidator.validate_record(row)
    assert is_valid is False
    assert code == "AMOUNT_EXCEEDS_MAX_LIMIT"


def test_schema_field_length_limit():
    """Verify string identifiers exceeding 64 characters are rejected."""
    long_id = "A" * 65
    row = {
        "event_id": long_id,
        "transaction_id": "TXN_001",
        "customer_id": "CUST_001",
        "product_id": "PROD_001",
        "event_type": "NEW",
        "amount": "100.00",
        "currency": "USD",
        "event_timestamp": "2026-11-10T12:00:00Z",
    }
    is_valid, reason, code, _ = SchemaValidator.validate_record(row)
    assert is_valid is False
    assert code == "FIELD_VALUE_TOO_LONG"


def test_schema_whitespace_only_field():
    """Verify whitespace-only required fields are caught and rejected as missing."""
    row = {
        "event_id": "evt_ws_1",
        "transaction_id": "   ",  # Whitespace only
        "customer_id": "CUST_001",
        "product_id": "PROD_001",
        "event_type": "NEW",
        "amount": "50.00",
        "currency": "USD",
        "event_timestamp": "2026-11-10T12:00:00Z",
    }
    is_valid, reason, code, _ = SchemaValidator.validate_record(row)
    assert is_valid is False
    assert code == "MISSING_REQUIRED_FIELD"


def test_schema_currency_code_boundary():
    """Verify currency code must be exactly 3 uppercase letters and in ISO 4217 allowlist."""
    invalid_currencies = ["US", "USDD", "usd", "123", "$$$", "", "ZZZ"]
    for curr in invalid_currencies:
        row = {
            "event_id": "evt_curr_1",
            "transaction_id": "TXN_CURR_1",
            "customer_id": "CUST_001",
            "product_id": "PROD_001",
            "event_type": "NEW",
            "amount": "50.00",
            "currency": curr,
            "event_timestamp": "2026-11-10T12:00:00Z",
        }
        is_valid, reason, code, _ = SchemaValidator.validate_record(row)
        assert is_valid is False
        assert code in ["INVALID_CURRENCY", "MISSING_REQUIRED_FIELD", "UNSUPPORTED_CURRENCY"]


def test_business_validator_special_characters():
    """Verify reference keys with prohibited injection characters are rejected."""
    bad_keys = ["CUST_!@#$", "CUST_<script>", "PROD_DROP_TABLE;--", "CUST_NULL", "PROD_NONE"]
    for key in bad_keys:
        data = {"customer_id": key, "product_id": "PROD_VALID", "transaction_id": "TXN_VALID"}
        is_valid, reason, code = BusinessValidator.validate_reference_keys(data)
        assert is_valid is False

