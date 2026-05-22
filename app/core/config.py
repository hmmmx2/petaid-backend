from functools import lru_cache

from pydantic import Field
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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_supabase(self) -> bool:
        """True when DATABASE_URL points at a Supabase host."""
        return "supabase." in self.database_url or "pooler.supabase.com" in self.database_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
