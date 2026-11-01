"""CivicEase API (FastAPI).

Stateless by design: no database, no sessions, no cookies, no files written. The browser
keeps the extracted scheme and the match result; the server only transforms what it is sent.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, discover, extract, ingest, llm, privacy, ratelimit, rules, tts, ui_i18n
from .explain import build_explanation
from .i18n import LANGUAGES
from .models import DetailsRequest, DiscoverRequest, ExplainRequest, MatchRequest, SpeakRequest
from .options import (BUSINESS_TYPES, CATEGORIES, FIELD_LABELS, GENDERS, OCCUPATIONS,
                      REQUIRED_PROFILE_FIELDS, STATES)

log = logging.getLogger("civicease")
privacy.install_log_filter()

app = FastAPI(
    title="CivicEase",
    version="1.0.0",
    description="Turns government scheme documents into plain-language, regional-language "
    "eligibility explainers. Informational only. Stores no personal data.",
)


# ------------------------------------------------------------------ cross-cutting

@app.middleware("http")
async def safety_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
    )
    return response


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in ("/api/health", "/api/config"):
        key = ratelimit.client_key(request.headers.get("x-forwarded-for"), request.client.host if request.client else None)
        wait = ratelimit.check(key)
        if wait:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(wait)},
                content={"error": "rate_limited",
                         "message": f"Too many requests. Please wait {wait} seconds and try again."},
            )
    return await call_next(request)


@app.exception_handler(ingest.IngestError)
async def ingest_error(_: Request, exc: ingest.IngestError):
    return JSONResponse(status_code=422, content={"error": exc.code, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    # Report where and why, never the submitted values (they may be personal).
    problems = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"error": "invalid_input", "message": "Some details are not valid.", "problems": problems},
    )


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    log.error("Unhandled error: %s", type(exc).__name__)  # class only, no request content
    return JSONResponse(
        status_code=500,
        content={"error": "server_error", "message": "Something went wrong. Please try again."},
    )


# ------------------------------------------------------------------ meta

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/config")
async def get_config():
    return {
        "ai_mode": "live" if llm.available() else "demo",
        "ai_provider": config.llm_provider(),
        "tts_provider": config.tts_provider(),
        "discovery": discover.available(),
        "languages": {k: {"name": v["name"], "native": v["native"], "bcp47": v["bcp47"],
                          "rtl": bool(v.get("rtl"))} for k, v in LANGUAGES.items()},
        "states": STATES,
        "occupations": OCCUPATIONS,
        "categories": CATEGORIES,
        "genders": GENDERS,
        "business_types": BUSINESS_TYPES,
        "required_fields": REQUIRED_PROFILE_FIELDS,
        "field_labels": FIELD_LABELS,
        "max_upload_mb": config.max_upload_bytes() // (1024 * 1024),
        "link_policy": config.allowed_url_suffixes() or "any public website",
        "web_search": config.search_provider() != "none",
    }


# ------------------------------------------------------------------ interface language

@app.get("/api/ui/{language}")
async def ui_strings(language: str):
    """All interface text in the chosen language (translated by the AI, cached in memory)."""
    if language not in LANGUAGES:
        return JSONResponse(status_code=404, content={"error": "bad_language", "message": "Unsupported language."})
    strings, translated = await ui_i18n.translate_ui(language)
    return {"language": language, "translated": translated, "strings": strings}


# ------------------------------------------------------------------ live discovery

def _discovery_off() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "discovery_unavailable",
            "message": "Live scheme search needs a Gemini key (or a Tavily/Brave search key). Add one in the "
            ".env file and restart. You can still upload a document or paste a link.",
        },
    )


@app.post("/api/discover")
async def discover_schemes(body: DiscoverRequest):
    """Find real, current schemes on official websites for the chosen level (national or state)."""
    if not discover.available():
        return _discovery_off()
    try:
        return await discover.find_schemes(body.query, body.level, body.state)
    except (llm.LLMError, discover.DiscoveryError) as exc:
        return JSONResponse(status_code=502, content={"error": "discovery_failed", "message": f"Live search failed. {exc}"})


@app.post("/api/scheme-details")
async def scheme_details(body: DetailsRequest):
    """Fetch the official details of one scheme and turn them into structured rules."""
    if not discover.available():
        return _discovery_off()
    started = time.perf_counter()
    try:
        scheme, sources = await discover.load_scheme(body.name, body.url, body.level, body.state)
    except (llm.LLMError, discover.DiscoveryError) as exc:
        return JSONResponse(status_code=502, content={"error": "discovery_failed", "message": f"Live search failed. {exc}"})
    return {"scheme": scheme, "sources": sources, "elapsed_ms": int((time.perf_counter() - started) * 1000)}


@app.post("/api/ingest")
async def ingest_document(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    text: Optional[str] = Form(None),
):
    """Accept exactly one of: a PDF upload, a link, or pasted text. Returns the structured scheme."""
    started = time.perf_counter()
    provided = [x for x in (file, (url or "").strip() or None, (text or "").strip() or None) if x]
    if len(provided) != 1:
        raise ingest.IngestError("Please provide one PDF, one link, or some pasted text.", "bad_request")

    if file is not None:
        limit = config.max_upload_bytes()
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise ingest.IngestError("That file is too large.", "too_large")
        if data[:5] == b"%PDF-":
            import asyncio
            document = await asyncio.to_thread(ingest.pdf_to_text, data)
        else:
            document = ingest.text_input(data.decode("utf-8", errors="ignore"))
        source = "uploaded file"
    elif url and url.strip():
        document = await ingest.fetch_url(url.strip())
        source = url.strip()[:500]
    else:
        document = ingest.text_input(text or "")
        source = "pasted text"

    scheme = await extract.extract_scheme(document, source)
    return {"scheme": scheme, "elapsed_ms": int((time.perf_counter() - started) * 1000)}


# ------------------------------------------------------------------ matching and output

@app.post("/api/match")
async def match(body: MatchRequest):
    data = body.profile.model_dump()
    missing = [f for f in REQUIRED_PROFILE_FIELDS if data.get(f) in (None, "")]
    if missing:
        return JSONResponse(
            status_code=422,
            content={
                "error": "missing_fields",
                "message": "Please fill in these details so we can check your eligibility.",
                "missing": missing,
                "labels": [FIELD_LABELS[f] for f in missing],
            },
        )
    # The profile exists only inside this call. It is not logged, cached or returned.
    return rules.evaluate(body.scheme, body.profile)


@app.post("/api/explain")
async def explain(body: ExplainRequest):
    return await build_explanation(body.scheme, body.match, body.language)


@app.post("/api/speak")
async def speak(body: SpeakRequest):
    if body.language not in LANGUAGES:
        return JSONResponse(status_code=400, content={"error": "bad_language", "message": "Unsupported language."})
    try:
        audio = await tts.synthesize(body.text, body.language)
    except tts.TTSError:
        return JSONResponse(
            status_code=503,
            content={
                "error": "voice_unavailable",
                "message": "Voice is not available right now. You can still read the summary, "
                "or use your device's own voice.",
                "fallback": "browser_speech",
            },
        )
    return Response(content=audio, media_type="audio/mpeg")


# ------------------------------------------------------------------ frontend (served last)

if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
