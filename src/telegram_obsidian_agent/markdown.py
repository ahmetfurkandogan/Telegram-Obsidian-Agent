import json
import re
from datetime import datetime
from pathlib import PurePosixPath

from .models import Analysis, Capture, RenderedNote
from .security import safe_filename


def _validated_folder(folder: str) -> str:
    path = PurePosixPath(folder)
    if not folder or path.is_absolute() or ".." in path.parts:
        raise ValueError("folder must be vault-relative")
    return str(path)


def build_vault_paths(folder: str, capture_id: str, original_name: str, title: str, captured_at: datetime) -> tuple[str, str]:
    folder = _validated_folder(folder)
    safe_original = safe_filename(original_name, "attachment")
    safe_title = safe_filename(title, capture_id).lower()
    year_month = f"{captured_at:%Y}/{captured_at:%m}"
    prefix = f"{folder}/{year_month}/{capture_id}"
    return f"{prefix}-{safe_original}", f"{prefix}-{safe_title}.md"


def render_note(analysis: Analysis, capture: Capture, captured_at: datetime, folder: str) -> RenderedNote:
    folder = _validated_folder(folder)
    if not capture.attachment_path.startswith(f"{folder}/") or not capture.note_path.startswith(f"{folder}/"):
        raise ValueError("note paths must stay under configured folder")
    tags = "\n".join(f"  - {json.dumps(tag, ensure_ascii=False)}" for tag in analysis.tags)
    content = (
        "---\n"
        f"title: {json.dumps(analysis.title, ensure_ascii=False)}\n"
        f"captured_at: {json.dumps(captured_at.isoformat(), ensure_ascii=False)}\n"
        f"source_type: {json.dumps(capture.source_type, ensure_ascii=False)}\n"
        f"original_name: {json.dumps(capture.original_name, ensure_ascii=False)}\n"
        f"attachment: {json.dumps(capture.attachment_path, ensure_ascii=False)}\n"
        "tags:\n"
        f"{tags}\n"
        "---\n\n"
        f"![[{capture.attachment_path}]]\n\n"
        "## Summary\n\n"
        f"{analysis.summary}\n\n"
        "## Content\n\n"
        f"{analysis.body}\n"
    )
    return RenderedNote(capture.note_path, content, analysis.title, capture.attachment_path)


def preview_text(rendered: RenderedNote, max_chars: int = 3500) -> str:
    marker = "\n\n[preview truncated]"
    if len(rendered.content) <= max_chars:
        return rendered.content
    if max_chars <= len(marker):
        return marker[-max_chars:]
    return rendered.content[: max_chars - len(marker)] + marker
