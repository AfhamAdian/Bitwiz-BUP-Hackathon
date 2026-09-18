import json
from typing import NamedTuple

import httpx

SNIPPET = 500


class LLMError(RuntimeError):
    pass


class ProviderResult(NamedTuple):
    text: str
    model: str
    usage: dict
    note: str = ""


def describe_exception(exc: BaseException) -> str:
    """httpx timeout/connect errors stringify to '', so always keep the class name."""
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else f"{type(exc).__name__} (no message)"


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
        raise LLMError(f"HTTP {response.status_code}: {response.text[:SNIPPET]}")

    return response.json(), response.headers


def pluck(body: dict, *path) -> str:
    try:
        value = body
        for key in path:
            value = value[key]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(
            f"unexpected response shape ({exc}): {json.dumps(body)[:SNIPPET]}"
        ) from exc
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
