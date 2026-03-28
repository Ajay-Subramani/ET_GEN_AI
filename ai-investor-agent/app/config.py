from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_db_url: str | None = None
    default_user_id: str = "user_default"
    default_symbol: str = "TATASTEEL"
    # Ollama (text brain)
    ollama_agent_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_text_model: str = "deepseek-r1:7b"
    ollama_timeout_s: float = 20.0
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_agent_enabled: bool = True
    openai_max_tool_rounds: int = 6

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
