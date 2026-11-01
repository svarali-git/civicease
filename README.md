# CivicEase

An AI civic navigator. Choose national or state schemes, find real current schemes on official government websites, check if you qualify, and hear a short explainer in one of 13 Indian languages.

**Informational only. It does not replace legal advice or an official government decision.**

## User flow
1. **Landing:** National schemes or State schemes (pick your state).
2. **Find a scheme:** type or speak a need, tap a topic, or show popular schemes. Results are fetched live from official sites (`gov.in`, `nic.in`) and shown with their sources.
3. **What we found:** the scheme's rules extracted into structured JSON.
4. **Check if you qualify:** anonymous profile form (the state you chose is prefilled).
5. **Result:** verdict, per-condition checks, documents, how to apply, and a voice explainer. The language menu is at the top right; changing it re-renders the result.

You can also use **Have your own scheme document**: upload a PDF, give a link, or paste text.

## How it works
- **Discover (live):** Gemini with Google Search grounding, told to rely only on official Indian government sites. Links are kept only if they point at `gov.in` or `nic.in`, other sources are dropped, and the sources are always shown. Nothing is cached, so results are fresh each time.
- **Fallback search:** without a Gemini key, a Tavily or Brave key can be used instead (results limited to official hosts, the chosen page is then fetched and read).
- **Extract:** the AI turns the official text into `Scheme` JSON. Without an AI key, a rule-based parser is used.
- **Match:** a deterministic rule engine (no `eval`, no AI) compares rules to the profile. Anything it cannot decide is flagged "check yourself", never approved.
- **Explain and speak:** translated bullets and a voice script. Voice comes from gTTS, ElevenLabs or OpenAI, with a device-voice fallback.
- The server is stateless and stores nothing.

## Run it
Prerequisites: Python 3.10+.

```bash
cd civicease/backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env       # then edit .env (see below)
python -m uvicorn app.main:app --port 8000
```
Open http://localhost:8000. API docs at `/docs`.

### Free option without Gemini: Groq plus Tavily
Groq (https://console.groq.com/keys, free tier, no card) does the reading and translating; Tavily finds the official pages. In `.env`:
```
LLM_PROVIDER=groq
GROQ_API_KEY=your-key
GROQ_MODEL=llama-3.3-70b-versatile
TAVILY_API_KEY=your-tavily-key
```
Any OpenAI-style service works with `LLM_PROVIDER=compatible` plus `COMPATIBLE_API_KEY`, `COMPATIBLE_BASE_URL` and `COMPATIBLE_MODEL`. Free tiers are small, so the app waits and retries short rate limits, reads at most 20,000 characters per document (`MAX_EXTRACT_CHARS`), and translates the interface one chunk at a time.

### Live search with Gemini

In `.env`:
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-3.8-flash
LLM_TIMEOUT_SECONDS=120
```
Get a key at https://aistudio.google.com/apikey. Restart the server after editing. Without a search-capable key, the app still works through "Have your own scheme document".

## Languages
English, Hindi, Bengali, Marathi, Telugu, Tamil, Gujarati, Urdu (right-to-left), Kannada, Odia, Malayalam, Punjabi, Assamese.

The language menu (top right) changes the **whole page**: buttons, labels, messages, state and option names, and the result. The interface text lives in `frontend/strings.en.json` and is translated by the AI on first use through `GET /api/ui/{language}` (about 160 short strings, cached in memory only; it contains no user data). Your choice is remembered in the browser. Without an AI key the page stays in English and says so, while result headings, verdicts and the disclaimer are still hand-written in every language. Scheme details are translated by the AI.

After changing interface text in `index.html` or `app.js`, run `python scripts/build_ui_strings.py` to refresh the strings file (a test fails if a key is missing).

## API
| Endpoint | Purpose |
|---|---|
| `GET /api/config` | Mode, languages, profile choices, whether live search is on |
| `GET /api/ui/{language}` | Interface text in that language (AI-translated, cached) |
| `POST /api/discover` `{level, state?, query?}` | Live scheme list with official sources |
| `POST /api/scheme-details` `{level, state?, name, url?}` | Official details as structured `Scheme` JSON |
| `POST /api/ingest` (multipart `file`, `url` or `text`) | Your own document to `Scheme` JSON |
| `POST /api/match` `{scheme, profile}` | Verdict; 422 `missing_fields` if required answers are absent |
| `POST /api/explain` `{scheme, match, language}` | Localised bullets and voice script |
| `POST /api/speak` `{text, language}` | MP3, or 503 with `fallback: browser_speech` |

## Privacy design
- No database, files, cookies or sessions, and no personal data is cached. (Only the public interface translations are cached in memory.)
- The profile has fixed choices only (no free text); unknown fields are rejected; errors never echo values.
- The AI and search services never receive the profile. Only the scheme name, the chosen state or level, and the scrubbed search words leave the server.
- Search text is scrubbed of phone, email, Aadhaar, PAN and PIN patterns. Request bodies are never logged.
- The form clears after the answer (unless "keep my answers" is ticked) and on page close.
- `Cache-Control: no-store`, strict Content Security Policy, no third-party scripts or fonts.

## Tests
```bash
cd backend && python -m pytest -q
```
58 offline tests: acceptance criteria, discovery (official-link filtering, state/national scope, fallbacks), languages, voice fallback, SSRF blocking, headers. Test PDFs live in `backend/tests/fixtures` (regenerate with `python scripts/make_sample_pdfs.py`).

## Known limitations
- **Not tested against the live Gemini, Tavily, Brave, OpenAI, Anthropic or ElevenLabs services** (no network or keys in the build environment). All of those paths were tested with mocked responses only. Run it once with your key before relying on it.
- **Live results are AI-assisted web search, not an official API.** They can be incomplete or wrong. The app shows sources and warns when none is official; always verify at the official website.
- Gemini's free tier has rate and daily limits, and Google changes model names often (update `GEMINI_MODEL`).
- Live search needs Gemini (Google Search) or Tavily/Brave. Anthropic, OpenAI, Groq and compatible keys work for extraction and translation but not for search.
- No free voice exists for Odia and Assamese; those use the device voice if available. Urdu uses gTTS.
- Interface and heading translations are AI-generated or hand-written and should be reviewed by native speakers. Error messages that come from the server stay in English.
- Scanned or custom-font PDFs (common for Tamil) cannot be read; there is no OCR.
- Rate limiting is basic and in memory (one server). Fine for a demo; use a gateway for heavy public use.

## Troubleshooting
- **"Live scheme search needs a Gemini key":** set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY`, then restart.
- **HTTP 404 about a model:** change `GEMINI_MODEL` to a current model name from AI Studio.
- **HTTP 429:** rate limit or no credit; wait or check your account.
- **ReadTimeout:** raise `LLM_TIMEOUT_SECONDS`; live search can take 20 to 60 seconds.
- **Page shows `{"detail":"Not Found"}`:** an old server is still running on that port, or the `frontend` folder is not next to `backend`. Use another port.

## Layout
```
backend/app/    main, discover, search_web, llm, ingest, extract, rules, explain, tts, i18n, privacy
backend/tests/  pytest suite and fixtures
frontend/       index.html, styles.css, app.js (no build step)
scripts/        make_sample_pdfs.py
```


## Deploy it (public link for a hackathon)
The app is one container serving both the API and the page. Secrets go in the host's environment settings, never in the code.

1. Put the project on GitHub (the `.gitignore` already keeps `.env` out). Never commit your keys.
2. **Render (free):** New > Blueprint > choose the repo. `render.yaml` sets everything up; paste your `GEMINI_API_KEY` (and `TAVILY_API_KEY` if you use it) when asked. Or New > Web Service > Docker.
   Other hosts that accept the `Dockerfile` work the same way: Railway, Fly.io, Google Cloud Run, Hugging Face Spaces (Docker).
3. Open the public URL, check `/api/health`, then try a search and a language change.
4. Free hosts sleep when idle, so the first load can take up to a minute. Open the site a few minutes before you present.

**Protect your quota:** a public site can be used by anyone, and each search spends your API quota. `RATE_LIMIT_PER_MINUTE` (per visitor) and `RATE_LIMIT_GLOBAL_PER_MINUTE` (everyone together) limit this. A visitor's address is hashed and kept in memory for one minute only. Set a spending limit in your AI provider's console too, and remove the key when the event ends.

The Docker and Render files have not been built or deployed from the build environment, so do a trial deploy early.
