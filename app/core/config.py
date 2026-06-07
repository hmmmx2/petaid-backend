from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development")
    database_url: str = Field(...)
    jwt_secret: str = Field(...)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=14)
    cors_origins: str = Field(default="http://localhost:3000")

    # Abuse prevention. Disable only in controlled test environments.
    rate_limit_enabled: bool = Field(default=True)

    # --- Database / Supabase tuning -------------------------------------- #
    db_ssl: bool = Field(default=False)
    db_statement_cache_size: int = Field(default=0)
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)

    # --- Cloudflare R2 Object Storage ------------------------------------ #
    # All fields optional so the app boots without R2 in development.
    r2_account_id: str | None = Field(default=None)
    r2_access_key_id: str | None = Field(default=None)
    r2_secret_access_key: str | None = Field(default=None)
    r2_bucket_name: str | None = Field(default=None)
    r2_endpoint_url: str | None = Field(default=None)
    r2_public_base_url: str | None = Field(default=None)

    @property
    def r2_enabled(self) -> bool:
        """True when all required R2 credentials are present."""
        return bool(
            self.r2_endpoint_url
            and self.r2_access_key_id
            and self.r2_secret_access_key
            and self.r2_bucket_name
        )

    # --- Transactional email (SMTP) -------------------------------------- #
    # Optional. When unset, the app still runs and code delivery falls back to
    # the dev behaviour (the code is surfaced in the API response outside
    # production). Works with any SMTP provider (SendGrid, Resend, Mailgun,
    # Amazon SES, Gmail, …). Port 465 uses implicit TLS; any other port uses
    # STARTTLS.
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_user: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    smtp_from: str | None = Field(default=None)  # e.g. "PetAid <noreply@yourdomain>"

    @property
    def email_enabled(self) -> bool:
        """True when SMTP is configured well enough to send mail."""
        return bool(self.smtp_host and (self.smtp_from or self.smtp_user))

    # --- Object storage (Supabase Storage) ------------------------------ #
    supabase_url: str = Field(default="")
    supabase_service_key: str = Field(default="")
    supabase_storage_bucket: str = Field(default="pet-media")

    # Production frontend origin(s) always allowed in addition to CORS_ORIGINS.
    _ALWAYS_ALLOWED_ORIGINS = ("https://petaid-frontend.vercel.app",)

    @property
    def cors_origins_list(self) -> list[str]:
        configured = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return list(dict.fromkeys([*configured, *self._ALWAYS_ALLOWED_ORIGINS]))

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    # Known weak/sample secrets that must never reach production.
    _WEAK_SECRETS = {"", "secret", "changeme", "dev", "test", "petaid", "supersecret"}

    @model_validator(mode="after")
    def _harden_production(self) -> "Settings":
        """Fail fast on insecure production configuration."""
        if self.is_production:
            secret = (self.jwt_secret or "").strip()
            if len(secret) < 32 or secret.lower() in self._WEAK_SECRETS:
                raise ValueError(
                    "JWT_SECRET must be a strong random value (>=32 chars) in production."
                )
            if "*" in self.cors_origins_list:
                raise ValueError("CORS origins must be an explicit allow-list in production.")
        return self

    @property
    def is_supabase(self) -> bool:
        """True when DATABASE_URL points at a Supabase host."""
        return "supabase." in self.database_url or "pooler.supabase.com" in self.database_url

    @property
    def storage_enabled(self) -> bool:
        """True when Supabase Storage is configured for image offload."""
        return bool(self.supabase_url and self.supabase_service_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
