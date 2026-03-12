from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    APP_NAME: str = "cospec-api"
    APP_VERSION: str = "0.1.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = False
    APP_LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]

    # Security / JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://cospec:cospec@localhost:5432/cospec"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Storage (S3/R2/MinIO)
    STORAGE_ENDPOINT_URL: str = "http://localhost:9000"
    STORAGE_ACCESS_KEY_ID: str = "minioadmin"
    STORAGE_SECRET_ACCESS_KEY: str = "minioadmin"
    STORAGE_BUCKET_NAME: str = "cospec"
    STORAGE_REGION: str = "us-east-1"
    STORAGE_DOWNLOAD_URL_TTL_SECONDS: int = 3600
    STORAGE_UPLOAD_URL_TTL_SECONDS: int = 900

    # Email/SMS (Brevo)
    BREVO_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "no-reply@cospec-telecom.com"
    EMAIL_FROM_NAME: str = "Cospec Telecomunicaciones"
    MAILPIT_SMTP_HOST: str = "localhost"
    MAILPIT_SMTP_PORT: int = 1025
    SMS_SENDER_NAME: str = "Cospec"
    SMS_ENABLED: bool = True

    # Geocoding
    GEOCODING_PROVIDER: str = "nominatim"
    NOMINATIM_USER_AGENT: str = "cospec-telecom-api/0.1.0"
    NOMINATIM_RATE_LIMIT_DELAY: float = 1.1

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    TELEGRAM_WEBHOOK_URL: str = ""
    TELEGRAM_ENABLED: bool = False

    # Workers (ARQ)
    ARQ_MAX_JOBS: int = 10
    ARQ_JOB_TIMEOUT: int = 300
    ARQ_QUEUE_NAME: str = "cospec_queue"

    # Rate limiting
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_REGISTER_PER_MINUTE: int = 5
    RATE_LIMIT_API_PER_MINUTE: int = 100

    # Export
    EXPORT_MAX_ROWS: int = 50000
    EXPORT_FILE_TTL_DAYS: int = 30

    # Attachments
    ATTACHMENT_MAX_SIZE_MB: int = 20
    ATTACHMENT_MAX_PER_TICKET: int = 10
    ATTACHMENT_ALLOWED_TYPES: list[str] = [
        "image/jpeg",
        "image/png",
        "image/heic",
        "application/pdf",
        "text/plain",
    ]

    # SSE
    SSE_KEEPALIVE_SECONDS: int = 30
    SSE_RECONNECT_WINDOW_SECONDS: int = 30

    # SLA defaults (hours)
    SLA_DEFAULT_CRITICAL_HOURS: int = 4
    SLA_DEFAULT_HIGH_HOURS: int = 8
    SLA_DEFAULT_MEDIUM_HOURS: int = 24
    SLA_DEFAULT_LOW_HOURS: int = 72

    # AI (Minimax)
    MINIMAX_API_KEY: str = ""
    MINIMAX_API_URL: str = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    MINIMAX_MODEL: str = "abab6.5s-chat"
    MINIMAX_TIMEOUT_SECONDS: int = 10
    AI_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
