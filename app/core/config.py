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
    # Require TLS to the database. Supabase mandates SSL; local docker does not.
    db_ssl: bool = Field(default=False)
    # Supabase's transaction pooler (pgBouncer) does not support prepared
    # statements, so asyncpg's statement cache must be disabled. Safe to keep
    # at 0 everywhere; only matters when going through a pooler.
    db_statement_cache_size: int = Field(default=0)
    # Connection pool sizing — keep small when behind Supabase's pooler.
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=10)

    # --- Object storage (Supabase Storage) ------------------------------ #
    # When both are set, uploaded image data-URLs are offloaded to a public
    # Supabase Storage bucket and the DB stores the public URL instead of the
    # inline base64. Unset → images stay inline (graceful fallback). The
    # service-role key is server-only and must never reach the frontend.
    supabase_url: str = Field(default="")
    supabase_service_key: str = Field(default="")
    supabase_storage_bucket: str = Field(default="pet-media")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    # Known weak/sample secrets that must never reach production.
    _WEAK_SECRETS = {"", "secret", "changeme", "dev", "test", "petaid", "supersecret"}

    @model_validator(mode="after")
    def _harden_production(self) -> "Settings":
        """Fail fast on insecure production configuration.

        A weak/short JWT secret or a wildcard CORS origin in production is a
        critical vulnerability (token forgery / CSRF surface), so we refuse to
        boot rather than start in an unsafe state.
        """
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
