import asyncio
import tempfile
from pathlib import Path

import pytest

from app import ingest, privacy, tts
from conftest import FARMER, SAMPLES


def test_unreadable_pdf_gives_friendly_error(client):
    with open(SAMPLES / "sample_scanned_like.pdf", "rb") as f:
        r = client.post("/api/ingest", files={"file": ("s.pdf", f, "application/pdf")})
    assert r.status_code == 422 and r.json()["error"] == "unreadable_document"
    r = client.post("/api/ingest", files={"file": ("bad.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    assert r.status_code == 422 and "message" in r.json()


def test_ingest_needs_exactly_one_source(client):
    assert client.post("/api/ingest", data={}).status_code == 422
    assert client.post("/api/ingest", data={"text": "x" * 200, "url": "https://a.gov.in"}).status_code == 422


def test_pasted_text_works(client):
    text = (SAMPLES / "sample_women_enterprise_scheme.txt").read_text()
    r = client.post("/api/ingest", data={"text": text})
    assert r.status_code == 200 and r.json()["scheme"]["name"].startswith("Mahila")


def test_missing_required_fields_prompt_user(client, farmer_scheme):
    r = client.post("/api/match", json={"scheme": farmer_scheme, "profile": {"state": "Tamil Nadu"}})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "missing_fields" and set(body["missing"]) == {"occupation", "annual_income_lakh", "category"}


def test_profile_rejects_free_text_and_unknown_values(client, farmer_scheme):
    r = client.post("/api/match", json={"scheme": farmer_scheme, "profile": {**FARMER, "name": "Ravi Kumar"}})
    assert r.status_code == 422 and "Ravi" not in r.text
    r = client.post("/api/match", json={"scheme": farmer_scheme, "profile": {**FARMER, "state": "Atlantis"}})
    assert r.status_code == 422 and "Atlantis" not in r.text


def test_ambiguous_conditions_are_flagged_not_approved(client):
    scheme = {"name": "X", "eligibility": [{"field": "age", "op": "gte", "value": 18, "text": "Adult"}]}
    r = client.post("/api/match", json={"scheme": scheme, "profile": FARMER}).json()
    assert r["verdict"] == "conditional" and r["results"][0]["status"] == "check"


def test_untranslated_scheme_is_labelled_not_faked(client, farmer_scheme):
    match = client.post("/api/match", json={"scheme": farmer_scheme, "profile": FARMER}).json()
    ex = client.post("/api/explain", json={"scheme": farmer_scheme, "match": match, "language": "ta"}).json()
    assert ex["notice"] == "translation_unavailable"
    assert ex["sections"]["what"]["items"][0] == farmer_scheme["summary"]  # original text, not a fake translation


def test_old_sample_routes_are_gone(client):
    assert client.get("/api/schemes").status_code == 404
    assert client.post("/api/search", json={"query": "farmer"}).status_code in (404, 405)


def test_voice_failure_falls_back_gracefully(client):
    r = client.post("/api/speak", json={"text": "hello", "language": "hi"})
    assert r.status_code == 503 and r.json()["fallback"] == "browser_speech"


def test_voice_success_returns_audio(client, monkeypatch):
    async def fake(text, lang):
        return b"ID3audio"
    monkeypatch.setattr(tts, "synthesize", fake)
    r = client.post("/api/speak", json={"text": "hello", "language": "ta"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"


def test_scrubber_catches_common_identifiers():
    clean, found = privacy.scrub_text("call 98765 43210 or a@b.com aadhaar 1234 5678 9012")
    assert {"PHONE", "EMAIL", "AADHAAR"} <= set(found) and "98765" not in clean


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://10.0.0.5/x", "ftp://example.com/x", "http://169.254.169.254/"])
def test_unsafe_links_are_blocked(url):
    with pytest.raises(ingest.IngestError):
        asyncio.run(ingest.fetch_url(url))


def test_server_writes_no_files(client, farmer_scheme):
    before = {p for p in Path(tempfile.gettempdir()).iterdir()}
    client.post("/api/match", json={"scheme": farmer_scheme, "profile": FARMER})
    after = {p for p in Path(tempfile.gettempdir()).iterdir()}
    assert not [p for p in after - before if p.suffix in (".json", ".db", ".sqlite")]


def test_security_headers_and_frontend(client):
    r = client.get("/api/health")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/").status_code == 200
