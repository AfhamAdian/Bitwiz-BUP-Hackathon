from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Comma-separated fallback chain, tried left to right. A provider may repeat:
    # "groq,groq,gemini,omniroute" uses GROQ_API_KEY1 then GROQ_API_KEY2.
    provider_order: str = "groq,groq,gemini,omniroute"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"

    groq_api_key: str = ""
    groq_api_key1: str = ""
    groq_api_key2: str = ""
    # Groq rate limits are per model per org, so a repeated groq slot only gains
    # headroom when it also uses a different model.
    groq_model: str = "openai/gpt-oss-120b"
    groq_model1: str = ""
    groq_model2: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"

    omniroute_api_key: str = ""
    omniroute_model: str = "auto"
    omniroute_base_url: str = "http://localhost:20128/v1"

    llm_timeout_seconds: float = 30.0
    llm_connect_timeout_seconds: float = 5.0

    def groq_keys(self) -> list[str]:
        explicit = [k for k in (self.groq_api_key1, self.groq_api_key2) if k]
        return explicit or ([self.groq_api_key] if self.groq_api_key else [])

    def groq_models(self) -> list[str]:
        explicit = [m for m in (self.groq_model1, self.groq_model2) if m]
        return explicit or [self.groq_model]

    def gemini_keys(self) -> list[str]:
        return [k for k in (self.gemini_api_key,) if k]

    def omniroute_keys(self) -> list[str]:
        return [k for k in (self.omniroute_api_key,) if k]


@lru_cache
def get_settings() -> Settings:
    return Settings()
