"""The whole interface changes language, not just the result."""
import json
import re
from pathlib import Path

import pytest

from app import llm, ui_i18n
from app.i18n import LANGUAGES
from app.options import BUSINESS_TYPES, CATEGORIES, GENDERS, OCCUPATIONS, STATES

FRONT = Path(__file__).resolve().parents[2] / "frontend"
ENGLISH = json.loads((FRONT / "strings.en.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fresh_cache():
    ui_i18n._cache.clear()


def test_every_text_key_used_by_the_page_and_script_exists():
    page = (FRONT / "index.html").read_text(encoding="utf-8")
    script = (FRONT / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r'data-i18n(?:-placeholder|-aria)?="([^"]+)"', page))
    used |= {k for k in re.findall(r'\bt\("([^"]+)"', script) if not k.endswith(".")}  # "topic." etc. are prefixes
    used |= set(re.findall(r'setBusy\(true, "([^"]+)"', script))
    used |= {f"topic.{k}" for k in re.search(r"TOPICS = \[(.*?)\]", script).group(1).replace('"', "").replace(" ", "").split(",")}
    assert used - set(ENGLISH) == set()
    for prefix, values in (("state", STATES), ("occ", OCCUPATIONS), ("cat", CATEGORIES), ("gen", GENDERS), ("biz", BUSINESS_TYPES)):
        assert {f"{prefix}.{v}" for v in values} <= set(ENGLISH)


def test_english_is_served_as_is(client):
    body = client.get("/api/ui/en").json()
    assert body["translated"] is True and body["strings"] == ENGLISH


def test_unknown_language_rejected(client):
    assert client.get("/api/ui/xx").status_code == 404


def test_without_ai_the_page_stays_english_and_says_so(client):
    body = client.get("/api/ui/hi").json()
    assert body["translated"] is False and body["strings"] == ENGLISH


def test_every_language_translates_all_strings_and_keeps_placeholders(client, monkeypatch):
    async def fake(system, user, max_tokens=4000):
        payload = json.loads(re.search(r"<strings>\n(.*)\n</strings>", user, re.S).group(1))
        return {k: "T:" + v for k, v in payload.items()}

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete_json", fake)
    for code in [c for c in LANGUAGES if c != "en"]:
        body = client.get(f"/api/ui/{code}").json()
        assert body["translated"] is True and set(body["strings"]) == set(ENGLISH)
        assert body["strings"]["scope.label.state"] == "T:State schemes: {state}"


def test_bad_model_output_falls_back_per_string(client, monkeypatch):
    async def fake(system, user, max_tokens=4000):
        payload = json.loads(re.search(r"<strings>\n(.*)\n</strings>", user, re.S).group(1))
        out = {k: "ok " + v for k, v in payload.items()}
        out["scope.label.state"] = "lost the placeholder"   # placeholder dropped
        out["tagline"] = ""                                  # empty
        return out

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete_json", fake)
    s = client.get("/api/ui/ta").json()["strings"]
    assert s["scope.label.state"] == ENGLISH["scope.label.state"] and s["tagline"] == ENGLISH["tagline"]
    assert s["find.search"] == "ok " + ENGLISH["find.search"]


def test_translations_are_cached_and_failures_are_not(client, monkeypatch):
    calls = {"n": 0}

    async def fake(system, user, max_tokens=4000):
        calls["n"] += 1
        payload = json.loads(re.search(r"<strings>\n(.*)\n</strings>", user, re.S).group(1))
        return dict(payload)

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete_json", fake)
    client.get("/api/ui/mr"); first = calls["n"]
    client.get("/api/ui/mr")
    assert calls["n"] == first  # second request served from memory

    async def boom(system, user, max_tokens=4000):
        raise llm.LLMError("HTTP 429: quota exceeded")

    monkeypatch.setattr(llm, "complete_json", boom)
    body = client.get("/api/ui/gu").json()
    assert body["translated"] is False and body["strings"] == ENGLISH
