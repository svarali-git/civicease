"""Live discovery by level (national or state), with the network mocked."""
import json

import pytest

from app import discover, ingest, llm, search_web
from conftest import SAMPLES

OFFICIAL = {"title": "myscheme.gov.in", "url": "https://vertexaisearch.example/redirect/1"}
OTHER = {"title": "randomblog.com", "url": "https://vertexaisearch.example/redirect/2"}


@pytest.fixture()
def gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")


def test_discovery_off_without_keys(client):
    r = client.post("/api/discover", json={"level": "national"})
    assert r.status_code == 503 and r.json()["error"] == "discovery_unavailable"
    assert client.get("/api/config").json()["discovery"] is False


def test_state_level_needs_a_valid_state(client):
    assert client.post("/api/discover", json={"level": "state"}).status_code == 422
    assert client.post("/api/discover", json={"level": "state", "state": "Atlantis"}).status_code == 422
    assert client.post("/api/discover", json={"level": "weird"}).status_code == 422


def test_grounded_discovery_keeps_only_official_links(client, gemini, monkeypatch):
    seen = {}

    async def fake(system, user, max_tokens=4000):
        seen["user"] = user
        data = {"schemes": [
            {"name": "Good Scheme", "summary": "Helps farmers.", "authority": "Agri Dept", "url": "https://agri.tn.gov.in/x"},
            {"name": "Phish Scheme", "summary": "x", "authority": "", "url": "https://evil-gov.in/x"},
            {"name": "Lookalike", "summary": "x", "authority": "", "url": "https://gov.in.evil.com/x"},
        ]}
        return json.dumps(data), [OFFICIAL, OTHER]

    monkeypatch.setattr(llm, "complete_grounded", fake)
    r = client.post("/api/discover", json={"level": "state", "state": "tamil nadu", "query": "farmer call 9876543210"})
    body = r.json()
    assert r.status_code == 200
    assert "Tamil Nadu" in seen["user"] and "9876543210" not in seen["user"]  # state used, phone scrubbed
    urls = {s["name"]: s["url"] for s in body["schemes"]}
    assert urls == {"Good Scheme": "https://agri.tn.gov.in/x", "Phish Scheme": "", "Lookalike": ""}
    assert [s["title"] for s in body["sources"]] == ["myscheme.gov.in"]
    assert body["unofficial_sources_ignored"] == 1 and body["personal_details_removed"] and body["verified"]


def test_national_scope_does_not_mention_a_state(client, gemini, monkeypatch):
    seen = {}

    async def fake(system, user, max_tokens=4000):
        seen["user"] = user
        return '{"schemes": []}', []

    monkeypatch.setattr(llm, "complete_grounded", fake)
    body = client.post("/api/discover", json={"level": "national", "state": "Kerala"}).json()
    assert "central" in seen["user"].lower() and "Kerala" not in seen["user"]
    assert body["schemes"] == [] and body["verified"] is False


def test_scheme_details_become_structured_rules(client, gemini, monkeypatch):
    sheet = (SAMPLES / "sample_farmer_scheme.txt").read_text()

    async def fake(system, user, max_tokens=4000):
        return sheet, [OFFICIAL]

    monkeypatch.setattr(llm, "complete_grounded", fake)
    r = client.post("/api/scheme-details", json={"level": "national", "name": "Farmer Scheme", "url": "https://www.myscheme.gov.in/s/x"})
    body = r.json()
    assert r.status_code == 200
    assert any(x["field"] == "annual_income_lakh" for x in body["scheme"]["eligibility"])
    assert body["scheme"]["official_sources"] == [OFFICIAL["url"]]


def test_no_official_source_adds_a_warning(client, gemini, monkeypatch):
    sheet = (SAMPLES / "sample_farmer_scheme.txt").read_text()

    async def fake(system, user, max_tokens=4000):
        return sheet, [OTHER]

    monkeypatch.setattr(llm, "complete_grounded", fake)
    body = client.post("/api/scheme-details", json={"level": "national", "name": "Farmer Scheme"}).json()
    assert "No official government source" in body["scheme"]["warnings"][0]


def test_search_service_failure_is_friendly(client, gemini, monkeypatch):
    async def boom(system, user, max_tokens=4000):
        raise llm.LLMError("HTTP 429: quota exceeded")

    monkeypatch.setattr(llm, "complete_grounded", boom)
    r = client.post("/api/discover", json={"level": "national"})
    assert r.status_code == 502 and "quota exceeded" in r.json()["message"]


def test_tavily_fallback_when_no_gemini_key(client, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    sent = {}

    async def fake_search(query, limit=6):
        sent["q"] = query
        return [{"title": "PM Sample Yojana", "url": "https://www.myscheme.gov.in/schemes/x", "snippet": "Help for farmers"}]

    async def fake_fetch(url):
        return (SAMPLES / "sample_farmer_scheme.txt").read_text()

    monkeypatch.setattr(search_web, "web_search", fake_search)
    monkeypatch.setattr(ingest, "fetch_url", fake_fetch)
    body = client.post("/api/discover", json={"level": "state", "state": "Kerala", "query": "farmer"}).json()
    assert "Kerala" in sent["q"] and body["schemes"][0]["url"].endswith("/schemes/x")
    detail = client.post("/api/scheme-details", json={"level": "state", "state": "Kerala", "name": "PM Sample Yojana",
                                                      "url": body["schemes"][0]["url"]}).json()
    assert detail["scheme"]["eligibility"]
    # a result without an official page cannot be opened
    r = client.post("/api/scheme-details", json={"level": "national", "name": "No Link"})
    assert r.status_code == 502


@pytest.mark.parametrize("url,ok", [
    ("https://agri.tn.gov.in/a", True), ("https://www.myscheme.gov.in/x", True), ("https://gov.in/x", True),
    ("https://evil-gov.in/x", False), ("https://gov.in.evil.com/x", False), ("javascript:alert(1)", False),
    ("ftp://agri.gov.in/x", False), ("", False),
])
def test_official_url_filter(url, ok):
    assert bool(discover.official_url(url)) is ok
