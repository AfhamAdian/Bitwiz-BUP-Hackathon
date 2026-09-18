import logging
import re
import time
from typing import Any

from app.config import get_settings
from app.utils.directive_validation import strict_json
from app.utils.llms import gemini, groq, omniroute
from app.utils.llm_base import (
    LLMError,
    ModelOutputError,
    ProviderResult,
    describe_exception,
)

logger = logging.getLogger(__name__)

PROVIDERS = {module.NAME: module for module in (gemini, groq, omniroute)}


def provider_chain() -> list[tuple[str, int]]:
    """Attempts from PROVIDER_ORDER as (provider, slot).

    A provider may repeat: the Nth occurrence takes the Nth API key. Any provider left
    out of PROVIDER_ORDER is still appended as a last resort.
    """
    configured = [
        name.strip().lower() for name in get_settings().provider_order.split(",") if name.strip()
    ]
    chain: list[tuple[str, int]] = []
    slots: dict[str, int] = {}

    for name in configured:
        if name not in PROVIDERS:
            continue
        slot = slots.get(name, 0)
        chain.append((name, slot))
        slots[name] = slot + 1

    chain += [(name, 0) for name in PROVIDERS if name not in slots]
    return chain


def _parse_json(result: ProviderResult) -> Any:
    original = result.text if isinstance(result.text, str) else ''
    cleaned = original.strip()
    fence = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', cleaned, re.S | re.I)
    if fence:
        cleaned = fence.group(1)
    try:
        return strict_json(cleaned)
    except (ValueError, RecursionError):
        raise ModelOutputError(original) from None


async def generate_json(system_prompt: str, user_prompt: str) -> Any:
    chain = provider_chain()
    logger.info("[llm] fallback chain: %s", " -> ".join(f"{n}#{s + 1}" for n, s in chain))
    failures = []

    for position, (name, slot) in enumerate(chain, start=1):
        provider = PROVIDERS[name]
        label = f"{name}#{slot + 1}"
        started = time.perf_counter()
        logger.info(
            "[llm] attempt %d/%d provider=%s model=%s",
            position, len(chain), label, provider.model(slot),
        )
        try:
            result = await provider.complete(system_prompt, user_prompt, slot)
            payload = _parse_json(result)
        except ModelOutputError:
            # Return to the repair loop with this output; don't silently fall back.
            raise
        except Exception as exc:
            detail = describe_exception(exc)
            failures.append(f"{label}: {detail}")
            logger.warning(
                "[llm] provider=%s FAILED after %.2fs -> %s",
                label, time.perf_counter() - started, detail,
            )
            continue

        logger.info(
            "[llm] provider=%s OK in %.2fs | upstream_model=%s | usage=%s%s",
            label, time.perf_counter() - started, result.model, result.usage or "n/a",
            f" | routing={result.note}" if result.note else "",
        )
        return payload

    logger.error("[llm] all attempts failed: %s", " | ".join(failures))
    raise LLMError("all LLM providers failed -> " + " | ".join(failures))
