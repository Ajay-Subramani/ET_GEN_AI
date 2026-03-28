from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_db_url: str | None = None
    default_user_id: str = "user_default"
    default_symbol: str = "TATASTEEL"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_agent_enabled: bool = True
    openai_max_tool_rounds: int = 6

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
