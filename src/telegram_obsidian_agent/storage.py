import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Capture


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class PendingStore:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS captures (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    staged_path TEXT NOT NULL,
                    attachment_path TEXT NOT NULL,
                    note_path TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    analysis_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def create(self, capture: Capture) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO captures (
                    id, chat_id, source_type, original_name, mime_type, staged_path,
                    attachment_path, note_path, content_sha256, extracted_text,
                    analysis_json, status, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capture.id,
                    capture.chat_id,
                    capture.source_type,
                    capture.original_name,
                    capture.mime_type,
                    capture.staged_path,
                    capture.attachment_path,
                    capture.note_path,
                    capture.content_sha256,
                    capture.extracted_text,
                    capture.analysis_json,
                    capture.status,
                    _timestamp(capture.created_at),
                    _timestamp(capture.expires_at),
                ),
            )

    def get(self, capture_id: str) -> Capture | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM captures WHERE id = ?", (capture_id,)).fetchone()
        if row is None:
            return None
        return Capture(
            id=row["id"],
            chat_id=row["chat_id"],
            source_type=row["source_type"],
            original_name=row["original_name"],
            mime_type=row["mime_type"],
            staged_path=row["staged_path"],
            attachment_path=row["attachment_path"],
            note_path=row["note_path"],
            content_sha256=row["content_sha256"],
            extracted_text=row["extracted_text"],
            analysis_json=row["analysis_json"],
            status=row["status"],
            created_at=_datetime(row["created_at"]),
            expires_at=_datetime(row["expires_at"]),
        )

    def mark_saved(self, capture_id: str) -> bool:
        return self._mark_status(capture_id, "saved")

    def mark_cancelled(self, capture_id: str) -> bool:
        return self._mark_status(capture_id, "cancelled")

    def _mark_status(self, capture_id: str, status: str) -> bool:
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE captures SET status = ? WHERE id = ? AND status = 'pending'",
                (status, capture_id),
            )
        return result.rowcount == 1

    def expire(self, now: datetime) -> int:
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE captures SET status = 'expired' WHERE status = 'pending' AND expires_at <= ?",
                (_timestamp(now),),
            )
        return result.rowcount

    def purge(self, before: datetime) -> int:
        with self._connect() as connection:
            result = connection.execute(
                "DELETE FROM captures WHERE status IN ('saved', 'cancelled', 'expired') AND expires_at <= ?",
                (_timestamp(before),),
            )
        return result.rowcount
