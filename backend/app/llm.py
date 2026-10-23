"""OpenRouter chat-completions call that returns one JSON object."""
from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.apiyi.com/v1"
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class LLMError(Exception):
    """An upstream failure, carried to the client as {code, error} with an HTTP status (never 429 or 503)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def ai_enabled() -> bool:
    return bool((os.getenv("API_KEY", "").strip() or os.getenv("OPENROUTER_API_KEY", "")).strip())


def _extract(text: str):
    # the reply may arrive wrapped in a code fence or with a sentence around it
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        value = json.loads(text[a:b + 1])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


async def complete_json(system: str, prompt: str):
    """Ask the model once (plus one free retry if the reply is not JSON). Returns a dict or None."""
    key = (os.getenv("API_KEY", "").strip() or os.getenv("OPENROUTER_API_KEY", "")).strip()
    if not key:
        raise LLMError(501, "misconfigured", "The AI service is not configured")
    body = {
        "model": (os.getenv("MODEL_NAME", "").strip() or os.getenv("OPENROUTER_MODEL", "")).strip() or DEFAULT_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }
    url = ((os.getenv("API_BASE_URL", "").strip() or os.getenv("OPENROUTER_BASE_URL", "")).strip() or DEFAULT_BASE_URL).rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "X-Title": "SG Wardrobe"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        for _ in range(2):
            try:
                r = await client.post(url, json=body, headers=headers)
            except httpx.TimeoutException:
                raise LLMError(504, "timeout", "The AI service took too long")
            except httpx.HTTPError:
                logger.exception("Could not connect to OpenRouter")
                raise LLMError(502, "offline", "Could not reach the AI service")
            if r.status_code in (401, 403):
                logger.error("OpenRouter rejected the API key (%s)", r.status_code)
                raise LLMError(501, "misconfigured", "The AI service is not configured")
            if r.status_code == 429:
                # upstream busy: never 429 to the browser, which reserves 429 for the club rate limit
                raise LLMError(502, "busy", "The AI service is busy")
            if r.status_code >= 400:
                logger.error("OpenRouter returned %s: %s", r.status_code, r.text[:300])
                raise LLMError(502, "failed", "The AI service returned an error")
            try:
                choice = r.json()["choices"][0]
                text = choice["message"].get("content") or ""
            except (ValueError, KeyError, IndexError, TypeError):
                logger.error("Unexpected OpenRouter response: %s", r.text[:300])
                raise LLMError(502, "failed", "The AI service returned an error")
            if choice.get("finish_reason") == "content_filter":
                raise LLMError(502, "refused", "The AI declined this request")
            parsed = _extract(text)
            if parsed is not None:
                return parsed
            logger.warning("Model reply was not JSON; retrying once")
    return None
