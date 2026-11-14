"""Application Configuration Module using Pydantic Settings."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite:///./data/yottaflex.db"

    # File and Directory storage
    DATA_INPUT_DIR: str = "./data/input"
    DATA_PROCESSED_DIR: str = "./data/processed"
    DATA_REJECTED_DIR: str = "./data/rejected"
    DATA_SAMPLE_DIR: str = "./data/sample"
    REPORTS_DIR: str = "./reports"

    # Baseline & Anomaly Alerting Thresholds
    BASELINE_VERSION: str = "v1.0"
    ALERT_VOLUME_DROP_PCT: float = 30.0          # Drop in batch volume > 30% triggers alert
    ALERT_VOLUME_SPIKE_PCT: float = 100.0        # Surge in batch volume > 100% triggers alert
    ALERT_NULL_RATE_INCREASE_PCT: float = 10.0  # Increase in null rate > 10% triggers alert
    ALERT_AMOUNT_DRIFT_PCT: float = 50.0        # Shift in mean amount > 50% triggers alert
    ALERT_REJECTION_RATE_MAX_PCT: float = 5.0   # Rejection rate > 5% triggers warning
    ALERT_FRESHNESS_MAX_SEC: float = 86400.0    # Freshness latency > 24 hours triggers alert

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def resolve_paths(self):
        """Ensure critical directories exist."""
        for path_str in [
            self.DATA_INPUT_DIR,
            self.DATA_PROCESSED_DIR,
            self.DATA_REJECTED_DIR,
            self.DATA_SAMPLE_DIR,
            self.REPORTS_DIR
        ]:
            Path(path_str).mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.resolve_paths()

