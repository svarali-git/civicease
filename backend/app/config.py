"""Runtime configuration. Everything is read from environment variables at call time,
so tests and deployments can change behaviour without re-importing modules."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR.parent / "data"
FRONTEND_DIR = APP_DIR.parent.parent / "frontend"


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def get_int(name: str, default: int) -> int:
    try:
        return int(get(name, str(default)))
    except ValueError:
        return default


LLM_PROVIDERS = ("anthropic", "openai", "gemini", "groq", "compatible")


def llm_provider() -> str:
    """One of LLM_PROVIDERS, or 'none' (demo mode with rule-based extraction)."""
    choice = get("LLM_PROVIDER", "auto").lower()
    if choice == "none":
        return "none"
    if choice in LLM_PROVIDERS:
        return choice if get(f"{choice.upper()}_API_KEY") else "none"
    for name in LLM_PROVIDERS:
        if get(f"{name.upper()}_API_KEY"):
            return name
    return "none"


def default_extract_chars() -> int:
    """How much document text to send to the model. Free tiers with small per-minute token caps need less."""
    return get_int("MAX_EXTRACT_CHARS", 20000 if llm_provider() in ("groq", "compatible") else 150000)


def tts_provider() -> str:
    """'gtts', 'elevenlabs', 'openai' or 'none' (text-only, browser voice fallback)."""
    choice = get("TTS_PROVIDER", "gtts").lower()
    if choice == "elevenlabs" and not (get("ELEVENLABS_API_KEY") and get("ELEVENLABS_VOICE_ID")):
        return "none"
    if choice == "openai" and not get("OPENAI_API_KEY"):
        return "none"
    return choice if choice in ("gtts", "elevenlabs", "openai", "none") else "none"


def max_upload_bytes() -> int:
    return get_int("MAX_UPLOAD_MB", 10) * 1024 * 1024


def allowed_url_suffixes() -> list[str]:
    raw = get("ALLOWED_URL_SUFFIXES")
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


DEFAULT_SEARCH_SUFFIXES = [".gov.in", ".nic.in"]


def search_provider() -> str:
    """'tavily', 'brave' or 'none' (used only as a fallback when there is no Gemini key)."""
    choice = get("SEARCH_PROVIDER", "auto").lower()
    if choice == "none":
        return "none"
    if choice in ("tavily", "brave"):
        return choice if get(f"{choice.upper()}_API_KEY") else "none"
    for name in ("tavily", "brave"):
        if get(f"{name.upper()}_API_KEY"):
            return name
    return "none"


def search_suffixes() -> list[str]:
    """Web results are kept only if their host ends with one of these."""
    return allowed_url_suffixes() or DEFAULT_SEARCH_SUFFIXES
