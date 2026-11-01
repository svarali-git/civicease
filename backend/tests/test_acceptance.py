"""Tests mapped to the three acceptance criteria in the specification."""
import logging
import time

from conftest import FARMER, SAMPLES


def test_ac1_pdf_parses_to_structured_criteria_within_15_seconds(client):
    start = time.perf_counter()
    with open(SAMPLES / "sample_farmer_scheme.pdf", "rb") as f:
        r = client.post("/api/ingest", files={"file": ("s.pdf", f, "application/pdf")})
    assert time.perf_counter() - start < 15
    assert r.status_code == 200
    scheme = r.json()["scheme"]
    fields = {(x["field"], x["op"]) for x in scheme["eligibility"]}
    assert ("occupation", "in") in fields and ("annual_income_lakh", "lte") in fields
    assert any(x["value"] == 2.5 for x in scheme["eligibility"] if x["field"] == "annual_income_lakh")
    assert scheme["documents"] and scheme["how_to_apply"] and scheme["benefits"]


def test_ac2_regional_language_explainer_matches_text(client, farmer_scheme, monkeypatch):
    from app import explain
    from app.i18n import LANGUAGES

    async def fake_translate(payload, language):
        # stand-in for the AI translation: same shape, text tagged with the language
        return {k: ([f"[{language}] {x}" for x in v] if isinstance(v, list) else f"[{language}] {v}")
                for k, v in payload.items()}

    monkeypatch.setattr(explain.llm, "available", lambda: True)
    monkeypatch.setattr(explain, "_translate", fake_translate)
    match = client.post("/api/match", json={"scheme": farmer_scheme, "profile": FARMER}).json()
    for lang in [c for c in LANGUAGES if c != "en"]:
        ex = client.post("/api/explain", json={"scheme": farmer_scheme, "match": match, "language": lang}).json()
        assert ex["notice"] == "" and ex["bcp47"].startswith(lang)
        assert ex["sections"]["what"]["items"][0].startswith(f"[{lang}]")
        # the voice script is built from the same text that is shown on screen
        assert ex["sections"]["what"]["items"][0] in ex["script"]
        assert ex["sections"]["how"]["items"][0] in ex["script"]
        assert ex["disclaimer"] in ex["script"]


def test_thirteen_languages_with_complete_labels():
    from app.i18n import LABELS, LANGUAGES
    assert len(LANGUAGES) == 13 and list(LANGUAGES)[0] == "en"
    for code in LANGUAGES:
        assert set(LABELS[code]) == set(LABELS["en"]) and all(LABELS[code].values())
    assert LANGUAGES["ur"]["rtl"] is True


def test_ac3_eligibility_flags_and_no_pii_retained(client, farmer_scheme, caplog):
    caplog.set_level(logging.DEBUG)
    ok = client.post("/api/match", json={"scheme": farmer_scheme, "profile": FARMER}).json()
    assert ok["verdict"] == "conditional"  # land and tax conditions need the user's confirmation
    assert not any(r["status"] == "fail" for r in ok["results"])

    rich = client.post("/api/match", json={"scheme": farmer_scheme, "profile": {**FARMER, "annual_income_lakh": 7.7}}).json()
    assert rich["verdict"] == "ineligible"
    wrong_job = client.post("/api/match", json={"scheme": farmer_scheme, "profile": {**FARMER, "occupation": "student"}}).json()
    assert wrong_job["verdict"] == "ineligible"

    assert "7.7" not in caplog.text and "Tamil Nadu" not in caplog.text
    assert "7.7" not in str(rich)  # profile is not echoed back
