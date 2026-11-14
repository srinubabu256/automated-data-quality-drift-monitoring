"""Alert severity enumeration and ranking utilities."""
from app.database.enums import AlertSeverity

SEVERITY_HIERARCHY = {
    AlertSeverity.CRITICAL.value: 5,
    AlertSeverity.HIGH.value: 4,
    AlertSeverity.WARNING.value: 3,
    AlertSeverity.MEDIUM.value: 2,
    AlertSeverity.LOW.value: 1,
    AlertSeverity.INFO.value: 0,
    "NONE": -1,
}


def get_highest_severity(severities: list[str]) -> str:
    """Returns the highest priority alert severity from a list of severities."""
    if not severities:
        return "NONE"
    return max(severities, key=lambda s: SEVERITY_HIERARCHY.get(str(s).upper(), -1))
