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

    # Drift Detection Thresholds (Configurable)
    DRIFT_VOLUME_WARNING_PCT: float = 20.0       # Volume drop/spike >= 20%
    DRIFT_VOLUME_CRITICAL_PCT: float = 50.0      # Volume drop/spike >= 50%
    DRIFT_NULL_RATE_WARNING_PP: float = 5.0      # Column null rate shift >= 5 percentage points
    DRIFT_NULL_RATE_HIGH_PP: float = 15.0        # Column null rate shift >= 15 percentage points
    DRIFT_NULL_RATE_CRITICAL_PP: float = 25.0    # Column null rate shift >= 25 percentage points
    DRIFT_PSI_MODERATE: float = 0.10             # PSI >= 0.10 implies moderate drift
    DRIFT_PSI_SIGNIFICANT: float = 0.20          # PSI >= 0.20 implies significant drift
    DRIFT_PSI_CRITICAL: float = 0.25             # PSI >= 0.25 implies critical drift
    DRIFT_KS_PVALUE_THRESHOLD: float = 0.05      # Significance level for 2-sample KS test
    DRIFT_CHISQUARE_PVALUE_THRESHOLD: float = 0.05 # Significance level for Chi-Square test
    DRIFT_MIN_SAMPLE_SIZE: int = 30              # Minimum sample size required for continuous distribution tests
    DRIFT_CHISQUARE_MIN_EXPECTED_COUNT: float = 5.0 # Cochran condition for Chi-Square expected frequencies

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

