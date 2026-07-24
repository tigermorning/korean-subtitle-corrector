<!-- lang-switcher:start -->
<p align="center">
  <a href="README.md">한국어</a>
  ·
  <a href="README.zh-CN.md">中文(简体)</a>
  ·
  <a href="README.zh-TW.md">中文(繁體)</a>
  ·
  <a href="README.ja.md">日本語</a>
  ·
  <a href="README.es.md">Español</a>
  ·
  <a href="README.ar.md">العربية</a>
</p>
<!-- lang-switcher:end -->

# Korean Spacing & Spelling Auto-Correction Tool

A tool that automatically corrects the word spacing and spelling of Korean documents in various formats — subtitles (.srt), plain text (.txt), and MS Word (.docx). It can be used in two ways: as a CLI or as a web API (FastAPI).

Decisions are based on the language norms of the National Institute of the Korean Language, the Standard Korean Dictionary, and Urimalsaem (the open dictionary). Items whose basis is uncertain are not corrected automatically; instead, the tool asks the user to confirm them.

For details, see [PRD.md](./PRD.md) (Korean).

## Status

Development complete. Both the CLI (`main.py`) and the web API (`subtitle_corrector/api.py`, FastAPI + `static/index.html`) are implemented, and the Supabase integration (saving/retrieving correction results) has been verified. For cloud deployment, see [DEPLOY.md](./DEPLOY.md).

## How to run (Windows)

### 1. Setup

```powershell
git clone https://github.com/tigermorning/korean-subtitle-corrector.git
cd korean-subtitle-corrector
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and fill in the following values (issued for free at the National Institute of the Korean Language's Open API portal):

- `STDICT_API_KEY` / `OPENDICT_API_KEY` / `KORNORMS_API_KEY` — API keys for the Standard Korean Dictionary, Urimalsaem, and the NIKL language-norms API. Without them the server still starts, but an error occurs when the correction feature is actually invoked.
- `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` — for saving correction results (optional). Even without them, correction itself works normally; only the save step is reported as failed.

### 2. Run as a web server (recommended — test directly in a browser)

```powershell
.venv\Scripts\uvicorn subtitle_corrector.api:app --reload
```

Open http://127.0.0.1:8000 in your browser → upload a file → check the correction results.

### 3. Run as a CLI

```powershell
.venv\Scripts\python main.py correct examples\sample.srt
```

## Tests

```
pip install -r requirements-dev.txt
pytest
```

The tests query the live Standard Korean Dictionary / Urimalsaem APIs in real time (they do not use statically captured responses), so `STDICT_API_KEY` / `OPENDICT_API_KEY` must be set in `.env` and network access is required. If they fail, first determine whether it is a code regression or an actual revision of the NIKL dictionaries (see PRD.md §5).

> 🤖 Machine-translated from the [Korean original](./README.md); not yet reviewed by a native speaker.
