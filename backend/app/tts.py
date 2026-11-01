"""Text-to-speech with graceful fallback.

Providers: gTTS (free, needs internet, no key), ElevenLabs, OpenAI. If synthesis fails or
times out the API reports `audio: null` and the UI falls back to the text summary and the
browser's built-in speech voice. Audio is generated in memory and never stored.
"""
import asyncio
import io
import logging

import httpx

from . import config

log = logging.getLogger("civicease.tts")


class TTSError(RuntimeError):
    pass


# gTTS has no Odia or Assamese voice; those fall back to the device voice in the browser.
GTTS_LANGS = {"en", "hi", "bn", "mr", "te", "ta", "gu", "ur", "kn", "ml", "pa"}


def _gtts_sync(text: str, lang: str) -> bytes:
    from gtts import gTTS  # imported lazily; keeps startup fast and offline tests simple

    buf = io.BytesIO()
    gTTS(text=text, lang=lang).write_to_fp(buf)
    return buf.getvalue()


async def _elevenlabs(text: str) -> bytes:
    voice = config.get("ELEVENLABS_VOICE_ID")
    async with httpx.AsyncClient(timeout=config.get_int("TTS_TIMEOUT_SECONDS", 20)) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
            headers={"xi-api-key": config.get("ELEVENLABS_API_KEY"), "accept": "audio/mpeg"},
            json={"text": text, "model_id": config.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")},
        )
        resp.raise_for_status()
        return resp.content


async def _openai(text: str) -> bytes:
    async with httpx.AsyncClient(timeout=config.get_int("TTS_TIMEOUT_SECONDS", 20)) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {config.get('OPENAI_API_KEY')}"},
            json={"model": config.get("OPENAI_TTS_MODEL", "tts-1"), "voice": "alloy", "input": text,
                  "response_format": "mp3"},
        )
        resp.raise_for_status()
        return resp.content


async def synthesize(text: str, language: str) -> bytes:
    """Return MP3 bytes, or raise TTSError."""
    provider = config.tts_provider()
    timeout = config.get_int("TTS_TIMEOUT_SECONDS", 20)
    try:
        if provider == "gtts":
            if language not in GTTS_LANGS:
                raise TTSError("No free voice for this language")
            return await asyncio.wait_for(asyncio.to_thread(_gtts_sync, text, language), timeout)
        if provider == "elevenlabs":
            return await _elevenlabs(text)
        if provider == "openai":
            return await _openai(text)
    except Exception as exc:
        log.warning("TTS failed (%s)", type(exc).__name__)
        raise TTSError("Voice generation failed") from exc
    raise TTSError("Voice generation is not configured")
