from app.config import get_settings
from app.utils.llm_base import ProviderResult, openai_chat, pick_key

NAME = "omniroute"


def model(slot: int = 0) -> str:
    return get_settings().omniroute_model


async def complete(system_prompt: str, user_prompt: str, slot: int = 0) -> ProviderResult:
    settings = get_settings()

    return await openai_chat(
        base_url=settings.omniroute_base_url,
        api_key=pick_key(settings.omniroute_keys(), slot, "OMNIROUTE_API_KEY"),
        model=settings.omniroute_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout=settings.llm_timeout_seconds,
        connect_timeout=settings.llm_connect_timeout_seconds,
        note_header="x-omniroute-decision",
    )
