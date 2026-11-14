# Telegram–Obsidian Enriched Capture Design

## Intent

Build a single-user, local Telegram bot that turns PDF and voice messages into searchable Obsidian notes. The bot preserves the original attachment, extracts useful text, generates a title/summary/tags, shows a preview, and writes to the vault only after explicit confirmation.

## Goals

- Accept Telegram PDF documents and voice messages.
- Save the original PDF or audio file in the Obsidian vault.
- Extract bounded text from PDFs.
- Transcribe voice messages through a configured transcription API.
- Generate a structured title, summary, tags, and body from extracted text.
- Show the generated note and attachment preview in Telegram.
- Require `Kaydet` confirmation before any vault write.
- Make retries safe and prevent accidental overwrites.
- Keep the process local with Telegram polling and Obsidian Local REST API.

## Non-goals

- Multi-user accounts, roles, invitations, or per-user vaults.
- Telegram webhooks or cloud deployment.
- OCR for scanned PDFs in the first version.
- Video, images, arbitrary files, or document conversion.
- Editing, deleting, or searching existing Obsidian notes.
- Automatic sending or sharing of captured content.

## Anti-goals

- Never save an attachment or note before confirmation.
- Never overwrite an existing vault file.
- Never expose bot, provider, or Obsidian credentials in logs or Telegram replies.
- Never send a full PDF or audio file to the LLM analysis endpoint.
- Never treat PDF text, transcription, or filenames as trusted instructions.

## Existing project

The repository contains an earlier text/URL design and plan, but no implementation. Those documents exclude PDF and voice handling. This design supersedes them for the enriched-capture project.

## Approaches

### Chosen: local polling bot with staged attachment and enrichment

The bot downloads each Telegram file to a private temporary directory, validates it, extracts PDF text or transcribes audio, asks an LLM for structured metadata, and stores a pending capture in SQLite. A Telegram preview asks for confirmation. On confirmation, the attachment and Markdown note are written using create-only operations.

This preserves originals while making notes searchable. Staging keeps the explicit-confirmation rule intact.

### Rejected: attachment-only capture

It is smaller, but voice messages and PDFs remain difficult to search. It does not meet the chosen enriched-capture goal.

### Rejected: cloud webhook worker

It adds deployment, public networking, secret management, and a vault gateway. The local vault and single-user scope do not need that complexity.

## User flow

```text
PDF or voice message
        ↓
chat_id authorization
        ↓
Telegram download to private temp file
        ↓
type, size, and content validation
        ↓
PDF text extraction OR voice transcription
        ↓
structured LLM analysis
        ↓
Markdown preview + attachment metadata
        ↓
SQLite pending capture
        ↓
Kaydet / İptal
        ↓
create-only attachment write + create-only note write
        ↓
success path or retryable failure
```

## Vault layout

```text
Telegram Inbox/
  2026/
    11/
      <capture-id>-<safe-name>.pdf
      <capture-id>-<safe-name>.ogg
      <capture-id>-<safe-title>.md
```

The note embeds its attachment with an Obsidian wikilink. It contains frontmatter for capture time, source type, original filename, attachment path, and tags. The body contains the generated summary, extracted/transcribed content, and processing metadata.

## Module ownership

- `config.py`: environment values, defaults, and limits.
- `models.py`: immutable capture, analysis, and pending-state types.
- `security.py`: chat authorization, filename/path validation, and size/type checks.
- `telegram_files.py`: Telegram file metadata and bounded download to staging.
- `extractors.py`: bounded PDF text extraction and audio transcription adapter.
- `llm.py`: structured analysis request and response validation.
- `markdown.py`: safe frontmatter, attachment embed, and note path generation.
- `storage.py`: SQLite pending captures, expiry, and idempotent state transitions.
- `obsidian.py`: create-only attachment and Markdown writes through Local REST API.
- `bot.py`: commands, message routing, previews, and confirmation callbacks.
- `main.py`: dependency wiring and polling startup.

## Data and state

Pending rows store the opaque capture ID, authorized chat ID, staged file path, source metadata, extracted/transcribed text, rendered note content, target vault paths, status, timestamps, and content hashes. Staged files remain outside the vault until confirmation.

Allowed states:

```text
pending → saved
pending → cancelled
pending → expired
pending → pending  (retry after a failed vault write)
```

The save transition is conditional on `status = 'pending'`. Repeated callbacks cannot create a second capture. If an attachment write succeeds and note writing fails, the attachment hash is checked on retry and the same file is reused; different content at the same path is a conflict.

## Invariants

1. Only the configured Telegram `chat_id` reaches file download or content processing.
2. Bot, transcription, LLM, and Obsidian secrets come only from environment variables.
3. PDF and audio downloads have independent byte limits and finite timeouts.
4. PDF files must pass a PDF signature/type check; unsupported media is rejected.
5. PDF extraction has page and text limits. Scanned PDFs return a clear “no extractable text” error.
6. Voice transcription receives only the staged audio file and bounded metadata.
7. Extracted text and transcription are untrusted data, not instructions.
8. No vault write happens before `Kaydet`.
9. Vault paths are generated internally and cannot contain traversal segments.
10. Attachment and note writes are create-only. Existing different content is never overwritten.
11. Pending captures expire after 15 minutes and their staged files are cleaned up.
12. Callback data contains only an opaque pending capture ID.
13. Logs contain event IDs and error classes, not message content or credentials.

## External interfaces

- Telegram Bot API: polling, file download, preview messages, inline callbacks.
- Obsidian Local REST API: create-only binary attachment and Markdown writes.
- Transcription API: multipart audio upload, configured model, bounded response.
- LLM API: structured JSON analysis from extracted/transcribed text only.

The transcription adapter uses a configured OpenAI-compatible multipart endpoint. The rest of the application does not depend on a provider SDK.

## Configuration

Required:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_ID`
- `OBSIDIAN_API_KEY`
- `TRANSCRIPTION_API_KEY`
- `LLM_API_KEY`

Optional defaults:

- `OBSIDIAN_BASE_URL=http://127.0.0.1:27123`
- `OBSIDIAN_FOLDER=Telegram Inbox`
- `TRANSCRIPTION_BASE_URL=https://api.openai.com/v1`
- `TRANSCRIPTION_MODEL=whisper-1`
- `LLM_BASE_URL=https://api.openai.com/v1`
- `LLM_MODEL=gpt-4o-mini`
- `DATABASE_PATH=data/agent.sqlite3`
- `MAX_PDF_BYTES=20000000`
- `MAX_AUDIO_BYTES=10000000`
- `MAX_PDF_PAGES=100`
- `MAX_EXTRACTED_CHARS=120000`
- `PENDING_TTL_SECONDS=900`

The transcription provider receives voice content. README must state this privacy boundary clearly.

## Verification

- Unit tests for config, authorization, file validation, filename/path safety, PDF extraction limits, and SQLite transitions.
- Contract tests for Telegram download handling, transcription requests, LLM JSON validation, and Obsidian create-only writes.
- Bot flow tests for unauthorized users, PDF preview, voice preview, confirmation, cancellation, expiry, repeated confirmation, and retry after partial vault failure.
- Local smoke test with one PDF and one voice message using the user’s Telegram bot and running Obsidian Local REST API.

## Builder decisions left

- Use Python 3.11+ with `python-telegram-bot`, `httpx`, `pypdf`, and `pytest`.
- Use `.ogg` Telegram voice files directly for transcription; reject providers that cannot accept them rather than adding an audio conversion service.
- Keep generated note and original attachment in the same year/month directory so the wikilink remains simple.
- Add OCR only as a later, separate feature if scanned PDFs matter.

## Resolved implementation decisions

- The LLM returns exactly `title`, `summary`, `tags`, and `body`. Title is 1–120 characters, summary is 1–1200 characters, body is at most 12000 characters, and tags contain at most 10 normalized lowercase kebab-case values.
- The preview sends title, summary, attachment name, and the first 2500 characters of the body. It states when the saved note contains more content. This stays below Telegram message limits.
- Obsidian writes use `PUT /vault/<vault-relative-path>` with Bearer authentication, `If-None-Match: *`, and the correct content type. `409` and `412` are duplicate-path conflicts; other failures remain retryable.
- Transcription uses `POST <TRANSCRIPTION_BASE_URL>/audio/transcriptions` with multipart `file` and `model` fields. A successful response must contain a string `text` field. The optional language setting is omitted in the first version.
- Only inline `Kaydet` and `İptal` buttons complete a pending capture. Callback chat ID must match the configured chat ID. No command-based confirmation is added.
- Names use Unicode normalization, safe-character filtering, bounded length, and a capture-ID prefix. Empty names fall back to `capture`. The generated ID prevents collisions.
- Empty or nearly empty extraction, transcription failure, or LLM failure does not discard the original file. The bot creates a deterministic fallback note, preserves available text, and still requires confirmation.
- Staged files are removed after cancellation, expiry, or successful vault completion. Pending rows stay for 30 days for audit and are then purged. Failed writes keep the pending row retryable until its 15-minute expiry.
