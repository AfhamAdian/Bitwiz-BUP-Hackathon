from app.config import get_settings
from app.utils.llm_base import ProviderResult, pick_key, pluck, post_json

NAME = "gemini"


def model(slot: int = 0) -> str:
    return get_settings().gemini_model


async def complete(system_prompt: str, user_prompt: str, slot: int = 0) -> ProviderResult:
    settings = get_settings()
    api_key = pick_key(settings.gemini_keys(), slot, "GEMINI_API_KEY")

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0, "response_mime_type": "application/json"},
    }
    body, _ = await post_json(
        f"{settings.gemini_base_url}/models/{settings.gemini_model}:generateContent",
        payload,
        {"x-goog-api-key": api_key},
        settings.llm_timeout_seconds,
        settings.llm_connect_timeout_seconds,
    )

    return ProviderResult(
        text=pluck(body, "candidates", 0, "content", "parts", 0, "text"),
        model=body.get("modelVersion") or settings.gemini_model,
        usage=body.get("usageMetadata") or {},
    )
