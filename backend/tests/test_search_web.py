"""The Tavily/Brave search module (fallback when no Gemini key is set)."""
import asyncio

import httpx

from app import search_web


def test_tavily_results_filtered_to_government_hosts(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "k")

    def handler(req):
        return httpx.Response(200, json={"results": [
            {"title": "Good", "url": "https://agri.tn.gov.in/a.pdf", "content": "<b>text</b>"},
            {"title": "Spam", "url": "https://evil.example.com/x", "content": "x"},
            {"title": "Dup", "url": "https://agri.tn.gov.in/a.pdf", "content": "x"},
        ]})

    orig = httpx.AsyncClient

    class Mock(orig):
        def __init__(self, *a, **k):
            super().__init__(*a, transport=httpx.MockTransport(handler), **k)

    monkeypatch.setattr(httpx, "AsyncClient", Mock)
    out = asyncio.run(search_web.web_search("farmers"))
    assert [o["url"] for o in out] == ["https://agri.tn.gov.in/a.pdf"] and out[0]["snippet"] == "text"
