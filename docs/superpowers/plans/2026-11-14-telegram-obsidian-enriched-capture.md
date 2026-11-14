# Telegram–Obsidian Enriched Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local single-user Telegram bot that saves PDFs and voice messages as searchable Obsidian notes with original attachments, without a second save decision.

**Architecture:** A polling Telegram adapter authorizes one chat, stages files outside the vault, extracts PDF text or calls a transcription endpoint, and asks an LLM for bounded structured metadata. SQLite stores pending captures during automatic create-only Obsidian writes.

**Tech Stack:** Python 3.11+, `python-telegram-bot`, `httpx`, `pypdf`, `python-dotenv`, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-telegram-obsidian-enriched-capture-design.md`

## Global Constraints

- Process only `TELEGRAM_ALLOWED_CHAT_ID`.
- Write authorized, validated captures automatically after processing.
- Use bounded PDF/audio downloads, PDF pages, extracted text, and finite network timeouts.
- Keep staged files outside the vault until validation completes and writing starts.
- Use `PUT /vault/<vault-relative-path>` with Bearer authentication and `If-None-Match: *`.
- Never overwrite existing files; treat `409` and `412` as conflicts.
- Remove staged files after expiry or successful completion.
- Do not log content, bot tokens, provider keys, or Obsidian keys.
- Preserve pending state after a failed vault write until the 15-minute expiry.

## Review Focus

- A Telegram file with a misleading filename or MIME type must be rejected unless its content signature is allowed; test in Task 2.
- A PDF with many pages or excessive extracted text must stop at configured limits; test in Task 3.
- A transcription or LLM response with malformed JSON or unexpected fields must not create a pending note; test in Tasks 3 and 4.
- A partial attachment write must not overwrite or duplicate a vault file; test in Tasks 5 and 6.

### Task 1: Project foundation, configuration, and capture store

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`
- Create: `src/telegram_obsidian_agent/__init__.py`
- Create: `src/telegram_obsidian_agent/config.py`
- Create: `src/telegram_obsidian_agent/models.py`
- Create: `src/telegram_obsidian_agent/storage.py`
- Test: `tests/test_config.py`, `tests/test_storage.py`

**Interfaces:**
- `Settings.from_env(environ: Mapping[str, str]) -> Settings`
- `Capture(id, chat_id, source_type, original_name, mime_type, staged_path, attachment_path, note_path, content_sha256, extracted_text, analysis_json, status, created_at, expires_at)`
- `PendingStore.create(capture: Capture) -> None`
- `PendingStore.get(capture_id: str) -> Capture | None`
- `PendingStore.mark_saved(capture_id: str) -> bool`
- `PendingStore.mark_cancelled(capture_id: str) -> bool`
- `PendingStore.expire(now: datetime) -> int`
- `PendingStore.purge(before: datetime) -> int`

- [ ] Write failing tests for required environment values, defaults, integer chat ID parsing, empty secrets, SQLite round-trip, conditional state transitions, expiry, and duplicate save.
- [ ] Run `pytest tests/test_config.py tests/test_storage.py -q`; expect failure because modules do not exist.
- [ ] Implement frozen dataclasses, exact defaults from the spec, SQLite schema, WAL mode, and conditional transitions.
- [ ] Run the focused tests; expect PASS.
- [ ] Commit `chore: add enriched capture foundation`.

### Task 2: Telegram staging and file validation

**Files:**
- Create: `src/telegram_obsidian_agent/security.py`
- Create: `src/telegram_obsidian_agent/telegram_files.py`
- Test: `tests/test_security.py`, `tests/test_telegram_files.py`

**Interfaces:**
- `assert_allowed_chat(chat_id: int, allowed_chat_id: int) -> None`
- `safe_filename(name: str, fallback: str) -> str`
- `validate_file_header(path: Path, source_type: SourceType) -> None`
- `TelegramFileStager.download(document_or_voice, destination_dir: Path) -> StagedFile`

- [ ] Test unauthorized chat IDs, traversal/control characters, PDF `%PDF` signature, OGG `OggS` signature, byte limits, and cleanup on failed downloads.
- [ ] Run the focused tests; expect failure before implementation.
- [ ] Implement bounded streaming downloads through the Telegram adapter, content-signature checks, SHA-256 calculation, and private staging paths.
- [ ] Run the focused tests; expect PASS.
- [ ] Commit `feat: stage and validate telegram attachments`.

### Task 3: PDF extraction and voice transcription

**Files:**
- Create: `src/telegram_obsidian_agent/extractors.py`
- Test: `tests/test_extractors.py`

**Interfaces:**
- `PdfTextExtractor.extract(path: Path) -> ExtractedText`
- `TranscriptionClient.transcribe(path: Path, mime_type: str) -> str`

- [ ] Test bounded PDF page count, bounded extracted characters, empty/scanned PDF handling, multipart transcription fields, response validation, timeout, and provider error mapping.
- [ ] Run the focused tests; expect failure before implementation.
- [ ] Implement `pypdf` extraction with page and character limits. Implement multipart `POST <base>/audio/transcriptions` with `file` and `model`, accepting only JSON containing string `text`.
- [ ] Run the focused tests; expect PASS.
- [ ] Commit `feat: extract pdf text and transcribe voice`.

### Task 4: LLM analysis and Markdown rendering

**Files:**
- Create: `src/telegram_obsidian_agent/llm.py`
- Create: `src/telegram_obsidian_agent/markdown.py`
- Test: `tests/test_llm.py`, `tests/test_markdown.py`

**Interfaces:**
- `LLMAnalyzer.analyze(text: str, source_type: SourceType, original_name: str) -> Analysis`
- `render_note(analysis: Analysis, capture: Capture, captured_at: datetime, folder: str) -> RenderedNote`
- `preview_text(rendered: RenderedNote, max_chars: int = 3500) -> str`

- [ ] Test exact JSON keys, title/summary/body bounds, tag normalization and count, malformed provider output, prompt-injection-as-data handling, safe YAML/frontmatter, path traversal rejection, unique filenames, attachment wikilink, and preview truncation.
- [ ] Run the focused tests; expect failure before implementation.
- [ ] Implement HTTP LLM adapter with bounded input and strict response validation. Render deterministic frontmatter and note paths under the configured folder; use fallback metadata when extracted text is empty.
- [ ] Run the focused tests; expect PASS.
- [ ] Commit `feat: generate enriched obsidian notes`.

### Task 5: Obsidian create-only adapter

**Files:**
- Create: `src/telegram_obsidian_agent/obsidian.py`
- Test: `tests/test_obsidian.py`

**Interfaces:**
- `ObsidianClient.write_attachment(note: RenderedNote, source_path: Path, mime_type: str, sha256: str) -> None`
- `ObsidianClient.write_note(note: RenderedNote) -> None`
- `ObsidianClient.healthcheck() -> None`

- [ ] Test Bearer authentication, vault-relative URL encoding, binary and Markdown content types, `If-None-Match: *`, success, conflicts, timeout, and error redaction.
- [ ] Run the focused tests; expect failure before implementation.
- [ ] Implement create-only PUT calls and conflict/error mapping. On an existing matching attachment hash, allow retry reuse; reject different content.
- [ ] Run the focused tests; expect PASS.
- [ ] Commit `feat: add create-only obsidian writer`.

### Task 6: Telegram automatic save flow

**Files:**
- Create: `src/telegram_obsidian_agent/bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- `build_application(settings: Settings, store: PendingStore, stager: TelegramFileStager, extractor: PdfTextExtractor, transcriber: TranscriptionClient, analyzer: LLMAnalyzer, obsidian: ObsidianClient) -> Application`

- [ ] Test unauthorized messages, direct PDF/voice saves, provider fallbacks, and retry after a partial Obsidian write.
- [ ] Run the focused tests; expect failure before implementation.
- [ ] Implement thin Telegram handlers. Authorize before processing, stage and enrich before creating a pending row, then save automatically under a lock.
- [ ] Run the focused tests; expect PASS.
- [ ] Commit `feat: add telegram enrichment flow`.

### Task 7: Runtime wiring and operator documentation

**Files:**
- Create: `src/telegram_obsidian_agent/main.py`
- Create: `README.md`
- Test: `tests/test_main.py`

**Interfaces:**
- `load_settings() -> Settings`
- `run() -> None`
- Module entry point: `python -m telegram_obsidian_agent`

- [ ] Test startup validation, directory creation, dependency wiring, and import without starting polling.
- [ ] Run the focused tests; expect failure before implementation.
- [ ] Implement environment loading, adapter wiring, expiry cleanup, handler registration, and polling behind `run()`.
- [ ] Document BotFather setup, chat ID discovery, Obsidian Local REST API setup, provider privacy, `.env` values, launch, tests, and PDF/voice smoke tests.
- [ ] Run `pytest -q`; expect PASS.
- [ ] Run `python -m compileall src`; expect PASS.
- [ ] Commit `feat: add runnable telegram obsidian agent`.

## Self-review

All spec goals map to Tasks 2–7. Automatic saving, no-overwrite, bounded processing, retry state, cleanup, and secret handling have dedicated interfaces or tests. OCR, cloud deployment, multi-user support, and arbitrary files remain outside the plan.
