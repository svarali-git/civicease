"""Thin LLM client (Anthropic, OpenAI or Gemini) over plain HTTPS.

Used for three things only: structured extraction from scheme text, translation of
plain-language explainers, and (Gemini only) live search of official government websites.
Prompts never contain user profile data.
"""
import json
import logging
import re

import httpx

from . import config

log = logging.getLogger("civicease.llm")


class LLMError(RuntimeError):
    pass


def available() -> bool:
    return config.llm_provider() != "none"


def search_available() -> bool:
    """Live web search is implemented through Gemini's Google Search grounding."""
    return config.llm_provider() == "gemini"


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model did not return JSON")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("Model returned invalid JSON") from exc


def _api_error(resp: httpx.Response) -> str:
    """The provider's own error message (e.g. 'invalid x-api-key'). Never includes our request."""
    try:
        err = resp.json().get("error", {})
        text = err.get("message") if isinstance(err, dict) else str(err)
    except Exception:
        text = ""
    return (text or resp.reason_phrase or "error")[:200]


def _timeout() -> int:
    return config.get_int("LLM_TIMEOUT_SECONDS", 90)


def _gemini_url() -> str:
    model = config.get("GEMINI_MODEL", "gemini-3.8-flash")
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _gemini_headers() -> dict:
    return {"x-goog-api-key": config.get("GEMINI_API_KEY"), "content-type": "application/json"}


def _gemini_candidate(resp: httpx.Response) -> dict:
    candidates = resp.json().get("candidates") or []
    if not candidates:
        raise LLMError("Gemini returned no answer (the reply may have been blocked)")
    return candidates[0]


def _gemini_text(candidate: dict) -> str:
    parts = (candidate.get("content") or {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts)


def _wrap_http_error(exc: httpx.HTTPError) -> LLMError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _api_error(exc.response)
        log.warning("LLM request failed: HTTP %s %s", status, detail)
        return LLMError(f"HTTP {status}: {detail}")
    # Log only the exception class, never request content.
    log.warning("LLM request failed: %s", type(exc).__name__)
    return LLMError(f"Request failed ({type(exc).__name__}). The AI service took too long or could not be reached.")


async def complete_json(system: str, user: str, max_tokens: int = 4000) -> dict:
    """Ask the configured model for a single JSON object and return it parsed."""
    provider = config.llm_provider()
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            if provider == "anthropic":
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": config.get("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": config.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
                        "max_tokens": max_tokens,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
                resp.raise_for_status()
                text = "".join(block.get("text", "") for block in resp.json().get("content", []))
            elif provider == "openai":
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {config.get('OPENAI_API_KEY')}"},
                    json={
                        "model": config.get("OPENAI_MODEL", "gpt-4o"),
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
            elif provider == "gemini":
                resp = await client.post(
                    _gemini_url(),
                    headers=_gemini_headers(),
                    json={
                        "systemInstruction": {"parts": [{"text": system}]},
                        "contents": [{"role": "user", "parts": [{"text": user}]}],
                        "generationConfig": {
                            "maxOutputTokens": max(max_tokens, 8000),
                            "responseMimeType": "application/json",
                            "temperature": 0,
                        },
                    },
                )
                resp.raise_for_status()
                text = _gemini_text(_gemini_candidate(resp))
                if not text:
                    raise LLMError("Gemini returned no text")
            else:
                raise LLMError("No LLM configured")
    except httpx.HTTPError as exc:
        raise _wrap_http_error(exc) from exc
    return parse_json(text)


async def complete_grounded(system: str, user: str, max_tokens: int = 4000) -> tuple[str, list[dict]]:
    """Gemini answer grounded in live Google Search results.

    Returns (text, sources) where sources are [{"title": domain, "url": link}].
    Search results are untrusted web content; callers must validate what they use.
    """
    if not search_available():
        raise LLMError("Live search needs a Gemini key. Set GEMINI_API_KEY and LLM_PROVIDER=gemini.")
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            resp = await client.post(
                _gemini_url(),
                headers=_gemini_headers(),
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "tools": [{"google_search": {}}],
                    "generationConfig": {"maxOutputTokens": max(max_tokens, 8000), "temperature": 0},
                },
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise _wrap_http_error(exc) from exc
    candidate = _gemini_candidate(resp)
    text = _gemini_text(candidate)
    if not text:
        raise LLMError("The search returned no text")
    sources, seen = [], set()
    for chunk in (candidate.get("groundingMetadata") or {}).get("groundingChunks", []):
        web = chunk.get("web") or {}
        key = web.get("title") or web.get("uri")
        if web.get("uri") and key not in seen:
            seen.add(key)
            sources.append({"title": web.get("title", ""), "url": web["uri"]})
    return text, sources
