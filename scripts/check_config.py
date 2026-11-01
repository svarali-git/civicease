"""Shows which settings CivicEase actually sees. Never prints the keys themselves.

Run from the backend folder:   python ../scripts/check_config.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import find_dotenv  # noqa: E402

from app import config, discover, llm  # noqa: E402

# Same search the app uses: starts in backend/app and walks up the folders.
env_file = find_dotenv(usecwd=False) or "(none found)"
print("Settings file used :", env_file)
print("Expected location  :", Path(__file__).resolve().parent.parent / ".env")
print()
for name in ("GEMINI_API_KEY", "TAVILY_API_KEY", "BRAVE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    print(f"{name:20}", "set" if config.get(name) else "NOT set")
print()
print("LLM_PROVIDER       :", config.get("LLM_PROVIDER", "auto"), "->", config.llm_provider())
print("SEARCH_PROVIDER    :", config.get("SEARCH_PROVIDER", "auto"), "->", config.search_provider())
print("Gemini model       :", config.get("GEMINI_MODEL", "gemini-3.8-flash"))
print()
print("Live scheme search :", "ON" if discover.available() else "OFF")
if not discover.available():
    print("\nWhy it is off: no Gemini key is active and no Tavily/Brave key was found,")
    print("or SEARCH_PROVIDER is set to none. Check the lines above.")
elif llm.search_available():
    print("Search will use    : Gemini (Google Search). If it hits a quota error, set LLM_PROVIDER=none to use Tavily.")
else:
    print("Search will use    :", config.search_provider())
