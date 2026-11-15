# Telegram Obsidian Agent

Send a PDF or voice message from Telegram. The bot validates it, extracts useful content, and saves the original file plus a Markdown note directly into Obsidian.

No second save decision is required.

## Features

- Single-chat authorization.
- PDF text extraction with page and character limits.
- Telegram voice-message transcription through an OpenAI-compatible endpoint.
- Optional AI title, summary, tags, and body enrichment.
- Automatic fallback when transcription or AI enrichment fails.
- Original attachment preserved beside its Markdown note.
- Create-only Obsidian writes. Existing files are never overwritten.
- Local SQLite state and private staging directory.

## Flow

```text
Telegram PDF or voice message
        ↓
Authorize configured chat
        ↓
Download, size-check, and signature-check
        ↓
Extract PDF text or transcribe voice
        ↓
Generate optional structured metadata
        ↓
Write attachment and Markdown note to Obsidian
        ↓
Send completion message to Telegram
```

## Requirements

- Python 3.11 or newer.
- Obsidian with the Local REST API plugin enabled.
- A Telegram bot created with [BotFather](https://t.me/BotFather).
- An OpenAI-compatible transcription endpoint for voice messages.
- An OpenAI-compatible chat-completions endpoint for enrichment.

## Installation

```bash
git clone <your-repository-url>
cd telegram-obsidian-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
cp .env.example .env
chmod 600 .env
```

Never commit `.env`. It contains credentials.

## Telegram setup

1. Open [BotFather](https://t.me/BotFather).
2. Run `/newbot` and copy the generated token into `TELEGRAM_BOT_TOKEN`.
3. Send `/start` to your bot from the phone chat you will use.
4. Put that chat's numeric ID in `TELEGRAM_ALLOWED_CHAT_ID`.

Only the configured chat can trigger downloads, transcription, or Obsidian writes.

## Obsidian setup

1. Open Obsidian and install the Local REST API community plugin.
2. Enable the plugin and copy its API key into `OBSIDIAN_API_KEY`.
3. Set `OBSIDIAN_BASE_URL` to the active local listener.

Typical values:

```text
# HTTP listener
OBSIDIAN_BASE_URL=http://127.0.0.1:27123
OBSIDIAN_VERIFY_TLS=true

# HTTPS listener with a local self-signed certificate
OBSIDIAN_BASE_URL=https://127.0.0.1:27124
OBSIDIAN_VERIFY_TLS=false
```

Use `OBSIDIAN_VERIFY_TLS=false` only for the local self-signed certificate.

## Configuration

Required secrets:

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_ID=
OBSIDIAN_API_KEY=
TRANSCRIPTION_API_KEY=
LLM_API_KEY=
```

Important optional settings are documented in `.env.example`:

| Variable | Purpose |
| --- | --- |
| `OBSIDIAN_FOLDER` | Vault-relative destination folder. |
| `TRANSCRIPTION_BASE_URL` | OpenAI-compatible transcription API base URL. |
| `TRANSCRIPTION_MODEL` | Transcription model name. |
| `LLM_BASE_URL` | OpenAI-compatible chat API base URL. |
| `LLM_MODEL` | Enrichment model name. |
| `DATABASE_PATH` | Local SQLite state database. |
| `STAGING_DIR` | Temporary file staging directory. |
| `MAX_PDF_BYTES` | Maximum PDF size. |
| `MAX_AUDIO_BYTES` | Maximum voice-message size. |
| `MAX_PDF_PAGES` | Maximum PDF pages to inspect. |
| `MAX_EXTRACTED_CHARS` | Maximum extracted text sent to processing. |
| `PENDING_TTL_SECONDS` | Cleanup deadline for failed pending writes. |

## Run

Keep Obsidian open, then start the bot:

```bash
source .venv/bin/activate
python -m telegram_obsidian_agent
```

Send a PDF or voice message from Telegram. The bot saves files under:

```text
<vault>/Telegram Inbox/YYYY/MM/
├── <capture-id>-<safe-name>.pdf or .ogg
└── <capture-id>-<safe-title>.md
```

The Markdown note embeds the original attachment and contains frontmatter, a summary, and extracted or transcribed content.

## Failure behavior

- A scanned PDF without a text layer still saves with a deterministic fallback note. OCR is not included.
- If transcription or AI enrichment fails, the original attachment still saves.
- If Obsidian is temporarily unavailable, the staged file and pending database record are retained until the cleanup deadline.
- Existing files are never overwritten. Conflicting paths are rejected.

## Privacy and security

- Telegram, transcription, LLM, and Obsidian credentials come from environment variables.
- `.env`, runtime data, staging files, and editor settings are ignored by Git.
- Only one configured Telegram chat is authorized.
- Downloads are bounded, signature-checked, hashed, and staged outside the vault.
- Extracted document text and voice audio are sent only to providers configured in `.env`.
- Do not send confidential content to providers whose privacy policy does not fit your use case.

## Development

Run the test suite and syntax check:

```bash
pytest -q
python -m compileall -q src
```

The main package layout is:

```text
src/telegram_obsidian_agent/
├── bot.py             Telegram routing and automatic save flow
├── config.py          Environment parsing and limits
├── extractors.py      PDF extraction and transcription client
├── llm.py             Structured AI enrichment
├── markdown.py        Safe note rendering and paths
├── obsidian.py        Create-only Local REST API writes
├── security.py        Authorization and file validation
├── storage.py         SQLite capture state
└── telegram_files.py  Bounded Telegram downloads
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Bot does not reply | Confirm the process is running and `TELEGRAM_ALLOWED_CHAT_ID` matches your phone chat. |
| Telegram authentication error | Regenerate the BotFather token and update `.env`. |
| Obsidian write failure | Confirm Obsidian is open, the Local REST API plugin is enabled, and the URL, port, API key, and TLS setting match. |
| AI quota or provider error | The original file still saves using fallback metadata. |

## License

No license has been selected yet. Add a license before publishing if others should be allowed to reuse the code.
