from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIA_", env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_ttl_minutes: int = 60
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt camera passwords at rest.
    secret_key: str
    default_retention_days: int = 7
    bootstrap_superadmin_email: str | None = None
    bootstrap_superadmin_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
