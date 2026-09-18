from app.config import get_settings
from app.utils.llm_base import ProviderResult, openai_chat, pick_key

NAME = "groq"


def model(slot: int = 0) -> str:
    models = get_settings().groq_models()
    return models[slot % len(models)]


async def complete(system_prompt: str, user_prompt: str, slot: int = 0) -> ProviderResult:
    settings = get_settings()

    return await openai_chat(
        base_url=settings.groq_base_url,
        api_key=pick_key(settings.groq_keys(), slot, "GROQ_API_KEY"),
        model=model(slot),
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=settings.llm_timeout_seconds,
        connect_timeout=settings.llm_connect_timeout_seconds,
    )
