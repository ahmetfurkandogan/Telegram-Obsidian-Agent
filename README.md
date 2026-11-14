# Telegram Obsidian Enriched Capture

Local Telegram bot for turning PDF documents and voice messages into searchable Obsidian notes.

## What it does

1. Accepts a PDF or Telegram voice message from one configured chat.
2. Saves the Telegram file to a private staging directory.
3. Extracts PDF text or transcribes voice through the configured transcription API.
4. Generates a title, summary, tags, and body through an OpenAI-compatible LLM endpoint.
5. Sends a Telegram preview.
6. Writes the original attachment and Markdown note to Obsidian only after `Kaydet`.

Scanned PDFs without an extractable text layer are preserved with a fallback note. OCR is not included.

## Requirements

- Python 3.11+
- Obsidian running with the Local REST API plugin enabled
- Telegram bot token from BotFather
- An OpenAI-compatible transcription endpoint accepting `.ogg` audio
- An OpenAI-compatible chat-completions endpoint

## Setup

```bash
cd "/Users/a.furkan/Documents/Telegram Obsidian Agent"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
cp .env.example .env
```

Set these values in `.env`:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_ID=...
OBSIDIAN_API_KEY=...
TRANSCRIPTION_API_KEY=...
LLM_API_KEY=...
```

Find the numeric chat ID by sending `/start` to the bot and reading the update during development, or use a trusted Telegram chat-ID utility. Keep only your own ID in `TELEGRAM_ALLOWED_CHAT_ID`.

Set the Obsidian Local REST API base URL and key. The default is `http://127.0.0.1:27123`.
If only the plugin’s HTTPS listener is active, use `https://127.0.0.1:27124` and set `OBSIDIAN_VERIFY_TLS=false` for its local self-signed certificate.

Voice audio and extracted document text are sent to the configured external providers. Use providers whose privacy policy fits the content.

## Run

```bash
python -m telegram_obsidian_agent
```

The computer must remain on, Obsidian must remain open, and the bot process must keep running. Notes and original files appear under `Telegram Inbox/YYYY/MM/`.

## Test

```bash
pytest -q
python -m compileall src
```

For a live smoke test, send one text-based PDF and one short voice message. Confirm each Telegram preview with `Kaydet`, then verify both the original files and Markdown notes in Obsidian. Send the same callback twice during a test; only one note should exist.

## Limits and safety

- Only one configured Telegram chat is authorized.
- PDF and audio size, PDF page, extracted text, and network time limits are configurable.
- Files stage outside the vault until confirmation.
- Existing vault files are never overwritten.
- Failed Obsidian writes remain retryable until the preview expires after 15 minutes.
- Secrets are read from environment variables and are not logged.
