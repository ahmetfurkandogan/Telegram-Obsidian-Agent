from datetime import datetime, timezone

import pytest

from telegram_obsidian_agent.markdown import build_vault_paths, preview_text, render_note
from telegram_obsidian_agent.models import Analysis, Capture, RenderedNote


def make_capture() -> Capture:
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    return Capture(
        id="cap-123",
        chat_id=123,
        source_type="pdf",
        original_name="report.pdf",
        mime_type="application/pdf",
        staged_path="/tmp/report.pdf",
        attachment_path="Telegram Inbox/2026/11/cap-123-report.pdf",
        note_path="Telegram Inbox/2026/11/cap-123-title.md",
        content_sha256="hash",
        extracted_text="source text",
        analysis_json="{}",
        status="pending",
        created_at=now,
        expires_at=now,
    )


def test_build_vault_paths_stays_under_folder_and_is_unique() -> None:
    attachment, note = build_vault_paths("Telegram Inbox", "cap-123", "report.pdf", "A title", datetime(2026, 11, 14))

    assert attachment == "Telegram Inbox/2026/11/cap-123-report.pdf"
    assert note == "Telegram Inbox/2026/11/cap-123-a-title.md"


def test_render_note_escapes_frontmatter_and_embeds_attachment() -> None:
    analysis = Analysis(
        title='A "quoted" title',
        summary="Summary\nwith newline",
        tags=["one", "two"],
        body="Body preserved",
    )

    rendered = render_note(analysis, make_capture(), datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc), "Telegram Inbox")

    assert rendered.title == analysis.title
    assert 'title: "A \\"quoted\\" title"' in rendered.content
    assert "![[Telegram Inbox/2026/11/cap-123-report.pdf]]" in rendered.content
    assert "Body preserved" in rendered.content


def test_render_note_rejects_traversal_folder() -> None:
    with pytest.raises(ValueError, match="folder"):
        render_note(Analysis("Title", "Summary", [], "Body"), make_capture(), datetime.now(timezone.utc), "../outside")


def test_preview_text_truncates_without_changing_saved_note() -> None:
    rendered = RenderedNote("note.md", "x" * 100, "Title", "file.pdf")

    preview = preview_text(rendered, max_chars=30)

    assert len(preview) <= 30
    assert "truncated" in preview.lower()
