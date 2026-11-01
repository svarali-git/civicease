"""Build frontend/strings.en.json, the canonical English interface text.

Keys come from data-i18n / data-i18n-placeholder / data-i18n-aria attributes in index.html,
plus the extra messages and option names below (used by app.js through t("key")).
Run from the project root after changing interface text:  python scripts/build_ui_strings.py
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from app.options import BUSINESS_TYPES, CATEGORIES, GENDERS, OCCUPATIONS, STATES  # noqa: E402

EXTRA = {
    "scope.label.national": "National schemes (Government of India)",
    "scope.label.state": "State schemes: {state}",
    "scope.err.state": "Please choose your state first.",
    "topic.farmers": "Farmers", "topic.women": "Women", "topic.students": "Students", "topic.health": "Health",
    "topic.housing": "Housing", "topic.jobs": "Jobs and skills", "topic.business": "Small business",
    "topic.seniors": "Senior citizens",
    "find.official": "Official page",
    "find.none": "No matching schemes were found. Try different words or a topic above.",
    "find.nosource": "No official government source was confirmed for these results. Please verify before relying on them.",
    "find.pii": "We removed personal details from your question. Please avoid typing them.",
    "find.loading": "Searching official websites. This can take up to a minute...",
    "find.failed": "Search failed.",
    "find.mic.err": "We could not hear that. Please try again or type your question.",
    "own.link.policy.any": "Public websites only. Links to private networks are blocked.",
    "own.link.policy.only": "Only these websites are accepted: {sites}",
    "own.choose_file": "Please choose a file first.",
    "own.loading": "Reading the document...",
    "own.failed": "We could not read that document.",
    "scheme.loading": "Reading the official details. This can take up to a minute...",
    "scheme.failed": "Could not load that scheme.",
    "scheme.notallowed": "Not allowed: {text}",
    "scheme.none": "No specific conditions were found. Please read the original document.",
    "scheme.read_in": "Read in {sec} s",
    "scheme.source": "Official source: {url}",
    "profile.missing": "Please fill in the missing details.",
    "profile.checking": "Checking...",
    "profile.failed": "Could not check eligibility.",
    "result.preparing": "Preparing the explanation...",
    "result.failed": "Could not prepare the explanation.",
    "result.note": "The scheme details could not be translated (an AI key is needed, or the AI service failed). Headings and the verdict are translated; the details stay in the original language.",
    "audio.preparing": "Preparing the voice...",
    "audio.press_play": "Press play to listen.",
    "audio.slow": "The voice took too long. You can read the summary above.",
    "audio.nodevice": "Your device has no voice for this language. Please read the summary above.",
    "choose": "Choose...",
    "mode.nosearch": "Live scheme search is off because no search key is set. You can still use \"Have your own scheme document\". Add a Gemini key to turn search on.",
    "mode.noai": "No AI key is set, so scheme details cannot be translated.",
    "err.server": "The service is not available right now.",
    "err.network": "Could not reach the server. Please check your connection and try again.",
    "ui.translating": "Translating the page...",
    "ui.failed": "The page could not be translated right now, so it stays in English.",
}
EXTRA.update({f"occ.{v}": v.replace("_", " ").capitalize() for v in OCCUPATIONS})
EXTRA.update({f"cat.{v}": (v.upper() if v != "general" else "General") for v in CATEGORIES})
EXTRA.update({f"gen.{v}": v.capitalize() for v in GENDERS})
EXTRA.update({f"biz.{v}": v.capitalize() for v in BUSINESS_TYPES})
EXTRA.update({f"state.{v}": v for v in STATES})


def main() -> None:
    page = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    strings: dict[str, str] = {}
    for m in re.finditer(r'data-i18n="([^"]+)"[^>]*>([^<]*)<', page):
        strings[m.group(1)] = " ".join(html.unescape(m.group(2)).split())
    for attr, key in (("data-i18n-placeholder", "placeholder"), ("data-i18n-aria", "aria-label")):
        for m in re.finditer(attr + r'="([^"]+)"[^>]*?' + key + r'="([^"]*)"', page):
            strings[m.group(1)] = html.unescape(m.group(2))
    strings.update(EXTRA)
    out = ROOT / "frontend" / "strings.en.json"
    out.write_text(json.dumps(strings, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out.name} with {len(strings)} strings")


if __name__ == "__main__":
    main()
