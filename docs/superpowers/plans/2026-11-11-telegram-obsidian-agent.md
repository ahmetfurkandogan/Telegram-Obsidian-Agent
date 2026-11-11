# Telegram Obsidian Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-user local Telegram bot that analyzes text and URLs, previews a Markdown note, and saves it to Obsidian after explicit confirmation.

**Architecture:** A Python polling process receives Telegram updates and authorizes one configured `chat_id`. Pure functions handle URL safety, analysis validation, Markdown rendering, and state transitions. Async adapters call the LLM and Obsidian Local REST API; SQLite stores pending confirmations and idempotency state.

**Tech Stack:** Python 3.11+, `python-telegram-bot`, `httpx`, OpenAI-compatible client, BeautifulSoup, SQLite, pytest, pytest-asyncio, respx.

**Spec:** `docs/superpowers/specs/2026-11-11-telegram-obsidian-agent-design.md`

## Global Constraints

- Accept only `http` and `https` URLs.
- Reject loopback, private, link-local, multicast, reserved, and unspecified destination IPs.
- Revalidate every redirect and follow at most three redirects.
- Enforce `MAX_SOURCE_BYTES` on source responses.
- Process only the configured `TELEGRAM_ALLOWED_CHAT_ID`.
- Require explicit `Kaydet` confirmation before Obsidian writes.
- Use `If-None-Match: *` for new Obsidian files; never overwrite existing notes.
- Keep bot, LLM, and Obsidian secrets in environment variables only.
- Keep pending confirmations valid for 15 minutes.
- Do not log message content or credentials.
- Do not add voice, OCR, multi-user, webhook, cloud deployment, or existing-note editing to MVP.

## Review Focus

- A URL resolving to `127.0.0.1`, a private IPv4 range, or an IPv6 local address must be rejected before connection; test in Task 2.
- A redirect from a public URL to a private address must be rejected; test in Task 2.
- Malformed or extra LLM JSON fields must not create a note; test in Task 3.
- A repeated `Kaydet` callback must create at most one note; test in Tasks 4 and 5.
- A failed Obsidian write must preserve a retryable pending state without exposing credentials; test in Tasks 4 and 5.

---

### Task 1: Project Foundation, Configuration, and Pending Store

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/telegram_obsidian_agent/__init__.py`
- Create: `src/telegram_obsidian_agent/config.py`
- Create: `src/telegram_obsidian_agent/models.py`
- Create: `src/telegram_obsidian_agent/storage.py`
- Test: `tests/test_config.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces `Settings.from_env(environ: Mapping[str, str]) -> Settings`.
- Produces `Analysis(title: str, summary: str, tags: list[str], source_url: str | None, body: str)`.
- Produces `PendingItem(id: str, chat_id: int, analysis_json: str, status: str, created_at: datetime, expires_at: datetime)`.
- Produces `PendingStore.create(item: PendingItem) -> None`, `get(item_id: str) -> PendingItem | None`, `mark_saved(item_id: str, note_path: str) -> bool`, `mark_cancelled(item_id: str) -> bool`, and `expire(now: datetime) -> int`.

- [ ] **Step 1: Write failing configuration tests**

Test that valid environment values load, required values are rejected, integer chat IDs are parsed, defaults are applied, and empty secrets fail with a clear `ValueError`.

- [ ] **Step 2: Run configuration tests**

Run: `pytest tests/test_config.py -q`

Expected: FAIL because `Settings` and `from_env` do not exist.

- [ ] **Step 3: Implement configuration and models**

Use frozen dataclasses. Keep default values exact: `OBSIDIAN_BASE_URL=http://127.0.0.1:27123`, `OBSIDIAN_FOLDER=Telegram Inbox`, `DATABASE_PATH=data/agent.sqlite3`, `MAX_SOURCE_BYTES=1000000`, `MAX_REDIRECTS=3`, and `PENDING_TTL_SECONDS=900`.

- [ ] **Step 4: Write failing SQLite state tests**

Test create/get, `pending -> saved`, `pending -> cancelled`, expired pending rows, duplicate save returning `False`, and a second save not changing the stored note path.

- [ ] **Step 5: Run storage tests**

Run: `pytest tests/test_storage.py -q`

Expected: FAIL because `PendingStore` is not implemented.

- [ ] **Step 6: Implement `PendingStore`**

Use SQLite with WAL mode. Store JSON analysis and ISO-8601 timestamps. All status transitions must be conditional on `status = 'pending'`.

- [ ] **Step 7: Run Task 1 tests**

Run: `pytest tests/test_config.py tests/test_storage.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example .gitignore src/telegram_obsidian_agent tests/test_config.py tests/test_storage.py
git commit -m "chore: add bot foundation and pending store"
```

### Task 2: URL Safety and Source Fetching

**Files:**
- Create: `src/telegram_obsidian_agent/security.py`
- Create: `src/telegram_obsidian_agent/fetcher.py`
- Test: `tests/test_security.py`
- Test: `tests/test_fetcher.py`

**Interfaces:**
- Produces `validate_source_url(raw_url: str, resolver: Callable[[str], list[str]] = ...) -> ParsedURL`.
- Produces `assert_allowed_chat(chat_id: int, allowed_chat_id: int) -> None`.
- Produces `SourceFetcher.fetch(url: str) -> SourceDocument`.

- [ ] **Step 1: Write failing URL security tests**

Cover invalid schemes, missing host, loopback IPv4, RFC1918 IPv4, link-local IPv4, IPv6 loopback, IPv6 private/link-local, and a public address. Assert rejection occurs before the HTTP client is called.

- [ ] **Step 2: Run security tests**

Run: `pytest tests/test_security.py -q`

Expected: FAIL because validators do not exist.

- [ ] **Step 3: Implement `validate_source_url` and chat authorization**

Normalize only the scheme and hostname needed for validation. Resolve all returned addresses. Reject any disallowed `ipaddress` classification. Keep authorization exact and integer-based.

- [ ] **Step 4: Write failing fetcher tests**

Test successful HTML text extraction, plain-text extraction, unsupported content type, response over the byte limit, timeout propagation, three-redirect limit, and redirect-to-private rejection.

- [ ] **Step 5: Run fetcher tests**

Run: `pytest tests/test_fetcher.py -q`

Expected: FAIL because `SourceFetcher` is not implemented.

- [ ] **Step 6: Implement `SourceFetcher`**

Use `httpx.AsyncClient` with finite connect/read/write/pool timeouts. Follow redirects manually so each target is validated. Stream the response and stop after `MAX_SOURCE_BYTES`. Use BeautifulSoup to remove script/style content and normalize visible text.

- [ ] **Step 7: Run Task 2 tests**

Run: `pytest tests/test_security.py tests/test_fetcher.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/telegram_obsidian_agent/security.py src/telegram_obsidian_agent/fetcher.py tests/test_security.py tests/test_fetcher.py
git commit -m "feat: add safe source fetching"
```

### Task 3: LLM Analysis and Markdown Rendering

**Files:**
- Create: `src/telegram_obsidian_agent/llm.py`
- Create: `src/telegram_obsidian_agent/markdown.py`
- Test: `tests/test_llm.py`
- Test: `tests/test_markdown.py`

**Interfaces:**
- Produces `LLMAnalyzer.analyze(input_text: str, source_url: str | None) -> Analysis`.
- Produces `render_note(analysis: Analysis, captured_at: datetime, folder: str) -> RenderedNote`.
- `RenderedNote` contains `path: str`, `content: str`, and `title: str`.

- [ ] **Step 1: Write failing LLM validation tests**

Test valid JSON mapping to `Analysis`, missing title, empty summary, non-string tags, more than 10 tags, oversized fields, malformed JSON, and provider error mapping to a safe application error.

- [ ] **Step 2: Run LLM tests**

Run: `pytest tests/test_llm.py -q`

Expected: FAIL because `LLMAnalyzer` is not implemented.

- [ ] **Step 3: Implement the LLM adapter**

Send a fixed instruction that treats source content as untrusted data. Request JSON with exactly `title`, `summary`, `tags`, `source_url`, and `body`. Parse and validate the response before constructing `Analysis`. Keep provider details behind the adapter.

- [ ] **Step 4: Write failing Markdown tests**

Test stable frontmatter keys, YAML-safe quotes/newlines, tag normalization, date-based unique filenames, folder traversal rejection, source URL inclusion, and body preservation.

- [ ] **Step 5: Run Markdown tests**

Run: `pytest tests/test_markdown.py -q`

Expected: FAIL because `render_note` is not implemented.

- [ ] **Step 6: Implement the renderer**

Generate a path below the configured folder only. Slugify the title to ASCII-safe characters where possible and append a timestamp plus short random suffix. Escape frontmatter values without allowing a newline to create a new key.

- [ ] **Step 7: Run Task 3 tests**

Run: `pytest tests/test_llm.py tests/test_markdown.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/telegram_obsidian_agent/llm.py src/telegram_obsidian_agent/markdown.py tests/test_llm.py tests/test_markdown.py
git commit -m "feat: analyze sources and render Obsidian notes"
```

### Task 4: Obsidian REST Adapter

**Files:**
- Create: `src/telegram_obsidian_agent/obsidian.py`
- Test: `tests/test_obsidian.py`

**Interfaces:**
- Produces `ObsidianClient.write_new(note: RenderedNote) -> str`.
- Produces `ObsidianClient.healthcheck() -> None`.

- [ ] **Step 1: Write failing REST contract tests**

With `respx`, test Bearer authentication, `PUT /vault/<percent-encoded-path>`, `Content-Type: text/markdown`, `If-None-Match: *`, success status, existing-file `412/409` handling, timeout, and safe error messages that contain no token.

- [ ] **Step 2: Run Obsidian tests**

Run: `pytest tests/test_obsidian.py -q`

Expected: FAIL because `ObsidianClient` is not implemented.

- [ ] **Step 3: Implement `ObsidianClient`**

Use the configured base URL and Bearer token. Allow only vault-relative paths produced by `render_note`. URL-encode each path segment. Return the vault-relative path on success. Map conflict to a retryable duplicate-path error.

- [ ] **Step 4: Run Task 4 tests**

Run: `pytest tests/test_obsidian.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/telegram_obsidian_agent/obsidian.py tests/test_obsidian.py
git commit -m "feat: add Obsidian REST writer"
```

### Task 5: Telegram Preview and Confirmation Flow

**Files:**
- Create: `src/telegram_obsidian_agent/bot.py`
- Test: `tests/test_bot.py`

**Interfaces:**
- Produces `build_application(settings: Settings, store: PendingStore, analyzer: LLMAnalyzer, obsidian: ObsidianClient, fetcher: SourceFetcher) -> Application`.
- Handler behavior: `/start` responds with usage; text handler creates a pending preview; `Kaydet` writes exactly once; `İptal` cancels; expired or unknown tokens do not write.

- [ ] **Step 1: Write failing bot flow tests**

Test unauthorized chat rejection, plain-text preview, URL fetch then preview, preview keyboard labels, save callback writing one note, repeated save callback writing zero additional notes, cancel callback, expired token, unknown token, and adapter error response.

- [ ] **Step 2: Run bot tests**

Run: `pytest tests/test_bot.py -q`

Expected: FAIL because handlers and application builder do not exist.

- [ ] **Step 3: Implement Telegram handlers**

Keep handler functions thin. Authorize before reading or processing message content. Store only the rendered note and analysis needed for confirmation. Put an opaque pending ID in callback data. Make save conditional on `mark_saved` so duplicate callbacks are harmless.

- [ ] **Step 4: Run Task 5 tests**

Run: `pytest tests/test_bot.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/telegram_obsidian_agent/bot.py tests/test_bot.py
git commit -m "feat: add Telegram preview confirmation flow"
```

### Task 6: Runtime Entry Point and Operator Documentation

**Files:**
- Create: `src/telegram_obsidian_agent/main.py`
- Create: `README.md`
- Create: `tests/test_main.py`

**Interfaces:**
- Produces `python -m telegram_obsidian_agent` entry point.
- Produces `load_settings() -> Settings` and `run() -> None`.

- [ ] **Step 1: Write failing runtime tests**

Test missing environment values produce a clear startup error, dependency wiring creates one store and one adapter per process, and `--help` or module import does not start polling during tests.

- [ ] **Step 2: Run runtime tests**

Run: `pytest tests/test_main.py -q`

Expected: FAIL because `main` is not implemented.

- [ ] **Step 3: Implement entry point**

Load settings, create the SQLite parent directory, construct adapters, register handlers, and start Telegram polling. Do not print secrets. Keep polling startup behind `run()` and `if __name__ == '__main__'`.

- [ ] **Step 4: Write README**

Document BotFather setup, chat ID discovery, `.env` setup, Obsidian Local REST API configuration, LLM provider configuration, launch command, unit tests, live smoke test, and troubleshooting. State that the process is local and the computer must remain on.

- [ ] **Step 5: Run Task 6 tests**

Run: `pytest tests/test_main.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/telegram_obsidian_agent/main.py README.md tests/test_main.py
git commit -m "feat: add runnable local Telegram bot"
```

### Task 7: Full Verification and Live Smoke Test

**Files:**
- Modify: `README.md`
- Test: `tests/test_integration.py`

- [ ] **Step 1: Add adapter-level integration test**

Exercise message → analysis → render → pending store → confirmed write using fake Telegram, LLM, and Obsidian adapters. Assert one note path and no duplicate writes.

- [ ] **Step 2: Run the complete test suite**

Run: `pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Run static checks**

Run: `python -m compileall -q src` and the project’s configured formatter/linter commands.

Expected: exit code `0` with no secret scan findings.

- [ ] **Step 4: Run manual smoke test**

With real environment values, send one plain text and one public URL from the allowed Telegram account. Confirm preview, cancel behavior, save behavior, note content, and duplicate callback behavior. Do not use sensitive content for the first smoke test.

- [ ] **Step 5: Record verification results**

Add commands and outcomes to `README.md`. Do not record tokens, full URLs containing secrets, or message content.

- [ ] **Step 6: Commit**

```bash
git add README.md tests/test_integration.py
git commit -m "test: verify end-to-end capture flow"
```

## Self-review result

- Spec coverage: all goals, exclusions, security invariants, error cases, and verification requirements map to Tasks 1–7.
- Type consistency: adapter signatures are defined before dependent tasks use them.
- Review focus: each listed failure mode has an owning test task.
- Proportion: plan describes interfaces, tests, exact limits, and commands without embedding implementation bodies.
- Remaining external prerequisite: the user must provide or configure Telegram, LLM, and Obsidian environment values before live smoke testing.
