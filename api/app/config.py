from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIA_", env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_ttl_minutes: int = 60
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt camera passwords at rest.
    secret_key: str
    default_retention_days: int = 7
    media_dir: str = "./media"
    purge_interval_seconds: int = 3600
    webhook_interval_seconds: int = 5
    # Tests only: allow webhooks to private/loopback addresses and plain http.
    webhook_allow_private: bool = False
    bootstrap_superadmin_email: str | None = None
    bootstrap_superadmin_password: str | None = None


    @field_validator("jwt_secret")
    @classmethod
    def _strong_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("AIA_JWT_SECRET must be at least 32 characters (python -c \"import secrets; print(secrets.token_urlsafe(48))\")")
        return v

    @field_validator("secret_key")
    @classmethod
    def _valid_fernet_key(cls, v: str) -> str:
        try:
            Fernet(v.encode())
        except Exception:
            raise ValueError("AIA_SECRET_KEY must be a Fernet key (python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
