from datetime import datetime, timedelta, timezone

from telegram_obsidian_agent.models import Capture
from telegram_obsidian_agent.storage import PendingStore


def capture(capture_id: str, *, expires_at: datetime) -> Capture:
    now = datetime.now(timezone.utc)
    return Capture(
        id=capture_id,
        chat_id=12345,
        source_type="pdf",
        original_name="source.pdf",
        mime_type="application/pdf",
        staged_path="/tmp/source.pdf",
        attachment_path="Telegram Inbox/source.pdf",
        note_path="Telegram Inbox/source.md",
        content_sha256="hash",
        extracted_text="text",
        analysis_json='{"title":"Source"}',
        status="pending",
        created_at=now,
        expires_at=expires_at,
    )


def test_pending_store_round_trip_and_conditional_transitions(tmp_path) -> None:
    store = PendingStore(tmp_path / "agent.sqlite3")
    item = capture("capture-1", expires_at=datetime.now(timezone.utc) + timedelta(minutes=15))

    store.create(item)

    assert store.get(item.id) == item
    assert store.mark_saved(item.id) is True
    assert store.mark_saved(item.id) is False
    assert store.get(item.id).status == "saved"
    assert store.mark_cancelled(item.id) is False


def test_pending_store_cancels_and_expires_pending_rows(tmp_path) -> None:
    store = PendingStore(tmp_path / "agent.sqlite3")
    now = datetime.now(timezone.utc)
    store.create(capture("cancel-me", expires_at=now + timedelta(minutes=15)))
    store.create(capture("expire-me", expires_at=now - timedelta(seconds=1)))

    assert store.mark_cancelled("cancel-me") is True
    assert store.expire(now) == 1
    assert store.get("cancel-me").status == "cancelled"
    assert store.get("expire-me").status == "expired"


def test_pending_store_purges_old_terminal_rows(tmp_path) -> None:
    store = PendingStore(tmp_path / "agent.sqlite3")
    now = datetime.now(timezone.utc)
    item = capture("old", expires_at=now - timedelta(days=31))
    store.create(item)
    assert store.mark_saved(item.id) is True

    assert store.purge(now - timedelta(days=30)) == 1
    assert store.get(item.id) is None


def test_pending_store_expires_and_returns_staged_paths(tmp_path) -> None:
    store = PendingStore(tmp_path / "agent.sqlite3")
    now = datetime.now(timezone.utc)
    item = capture("expire-with-file", expires_at=now - timedelta(seconds=1))
    store.create(item)

    assert store.expire_and_get_staged_paths(now) == ["/tmp/source.pdf"]
    assert store.get(item.id).status == "expired"
