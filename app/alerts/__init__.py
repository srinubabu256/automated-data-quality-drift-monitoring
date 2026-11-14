"""Alerts package exporting anomaly detection engine and severity utilities."""
from app.alerts.alert_engine import AlertEngine
from app.alerts.engine import AlertEngine as Engine
from app.alerts.severity import SEVERITY_HIERARCHY, AlertSeverity, get_highest_severity

__all__ = [
    "AlertEngine",
    "Engine",
    "AlertSeverity",
    "SEVERITY_HIERARCHY",
    "get_highest_severity",
]
