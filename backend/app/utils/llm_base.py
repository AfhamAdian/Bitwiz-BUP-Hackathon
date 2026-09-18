from typing import NamedTuple

import httpx


class LLMError(RuntimeError):
    pass


class ModelOutputError(LLMError):
    """Invalid completed output, retained only for a targeted repair prompt."""
    def __init__(self, previous_output):
        self.previous_output = previous_output
        super().__init__('Model returned invalid JSON.')


class ProviderResult(NamedTuple):
    text: str
    model: str
    usage: dict
    note: str = ""


def describe_exception(exc: BaseException) -> str:
    """Log the error category without echoing provider bodies or credential values."""
    return type(exc).__name__


def pick_key(keys: list[str], slot: int, env_name: str) -> str:
    """Slot N of a repeated provider takes the Nth key, wrapping if fewer keys exist."""
    if not keys:
        raise LLMError(f"{env_name} is not set")
    return keys[slot % len(keys)]


async def post_json(
    url: str, payload: dict, headers: dict, timeout: float, connect_timeout: float = 5.0
) -> tuple[dict, httpx.Headers]:
    limits = httpx.Timeout(timeout, connect=min(connect_timeout, timeout))
    async with httpx.AsyncClient(timeout=limits) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        raise LLMError(f"HTTP {response.status_code}")

    return response.json(), response.headers


def pluck(body: dict, *path) -> str:
    try:
        value = body
        for key in path:
            value = value[key]
    except (KeyError, IndexError, TypeError):
        raise LLMError('Unexpected provider response shape.') from None
    return value


async def openai_chat(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: float,
    connect_timeout: float = 5.0,
    note_header: str = "",
) -> ProviderResult:
    """Shared caller for OpenAI-compatible gateways (Groq, OmniRoute)."""
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    body, headers = await post_json(
        f"{base_url.rstrip('/')}/chat/completions",
        payload,
        {"Authorization": f"Bearer {api_key}"},
        timeout,
        connect_timeout,
    )
    return ProviderResult(
        text=pluck(body, "choices", 0, "message", "content"),
        model=body.get("model") or model,
        usage=body.get("usage") or {},
        note=headers.get(note_header, "") if note_header else "",
    )
