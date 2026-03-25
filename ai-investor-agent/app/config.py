from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_db_url: str | None = None
    default_user_id: str = "demo_moderate"
    default_symbol: str = "TATASTEEL"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
