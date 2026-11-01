"""AI provider plumbing with the network mocked: Groq, generic OpenAI-compatible, retries."""
import asyncio
import json

import httpx
import pytest

from app import config, llm


ORIGINAL_CLIENT = httpx.AsyncClient  # captured once so repeated calls do not wrap a wrapper


def run_with(monkeypatch, handler, coro_factory):
    class Mock(ORIGINAL_CLIENT):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=httpx.MockTransport(handler), **k)

    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    return asyncio.run(coro_factory())


def ok_chat(content='{"a": 1}'):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture()
def no_sleep(monkeypatch):
    waited = []

    async def fake(seconds):
        waited.append(seconds)

    monkeypatch.setattr(llm.asyncio, "sleep", fake)
    return waited


def test_groq_request_goes_to_groq_with_key_and_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    monkeypatch.setenv("GROQ_MODEL", "some-model")
    seen = {}

    def handler(req):
        seen.update(url=str(req.url), auth=req.headers["authorization"], body=json.loads(req.content))
        return ok_chat()

    out = run_with(monkeypatch, handler, lambda: llm.complete_json("sys", "user"))
    assert out == {"a": 1}
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer gk" and seen["body"]["model"] == "some-model"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert config.llm_provider() == "groq" and llm.available() and not llm.search_available()


def test_generic_compatible_provider_uses_custom_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "compatible")
    monkeypatch.setenv("COMPATIBLE_API_KEY", "ck")
    monkeypatch.setenv("COMPATIBLE_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("COMPATIBLE_MODEL", "m1")
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return ok_chat()

    run_with(monkeypatch, handler, lambda: llm.complete_json("s", "u"))
    assert seen["url"] == "https://example.test/v1/chat/completions"


def test_json_mode_is_dropped_when_the_model_rejects_it(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"message": "response_format not supported"}})
        return ok_chat('```json\n{"a": 2}\n```')

    assert run_with(monkeypatch, handler, lambda: llm.complete_json("s", "u")) == {"a": 2}
    assert bodies == [True, False]


def test_short_rate_limit_is_waited_out_and_retried(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": {"message": "slow down"}})
        return ok_chat()

    assert run_with(monkeypatch, handler, lambda: llm.complete_json("s", "u")) == {"a": 1}
    assert calls["n"] == 2 and no_sleep == [3.0]


def test_daily_quota_is_not_waited_out(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "3600"}, json={"error": {"message": "daily limit reached"}})

    with pytest.raises(llm.LLMError, match="HTTP 429: daily limit reached"):
        run_with(monkeypatch, handler, lambda: llm.complete_json("s", "u"))
    assert calls["n"] == 1 and no_sleep == []


def test_retry_gives_up_after_three_tries(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "1"}, json={"error": {"message": "busy"}})

    with pytest.raises(llm.LLMError):
        run_with(monkeypatch, handler, lambda: llm.complete_json("s", "u"))
    assert calls["n"] == 3


def test_existing_providers_still_work_through_the_shared_sender(monkeypatch):
    seen = []

    def handler(req):
        seen.append(str(req.url))
        if "anthropic" in str(req.url):
            return httpx.Response(200, json={"content": [{"text": '{"p": "anthropic"}'}]})
        if "googleapis" in str(req.url):
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"p": "gemini"}'}]}}]})
        return ok_chat('{"p": "openai"}')

    for name, key in (("anthropic", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("openai", "OPENAI_API_KEY")):
        monkeypatch.setenv("LLM_PROVIDER", name)
        monkeypatch.setenv(key, "k")
        assert run_with(monkeypatch, handler, lambda: llm.complete_json("s", "u")) == {"p": name}


def test_grounded_search_goes_through_the_sender_too(monkeypatch, no_sleep):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, headers={"retry-after": "1"}, json={"error": {"message": "overloaded"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "hello"}]},
                                                         "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://x", "title": "a.gov.in"}}]}}]})

    text, sources = run_with(monkeypatch, handler, lambda: llm.complete_grounded("s", "u"))
    assert text == "hello" and sources == [{"title": "a.gov.in", "url": "https://x"}]


def test_small_free_tiers_get_a_smaller_document_cap(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    assert config.default_extract_chars() == 20000
    monkeypatch.setenv("MAX_EXTRACT_CHARS", "5000")
    assert config.default_extract_chars() == 5000
    monkeypatch.delenv("MAX_EXTRACT_CHARS")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert config.default_extract_chars() == 150000
