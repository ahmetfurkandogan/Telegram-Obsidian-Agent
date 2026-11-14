from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SourceType(StrEnum):
    PDF = "pdf"
    VOICE = "voice"


@dataclass(frozen=True)
class Analysis:
    title: str
    summary: str
    tags: list[str]
    body: str


@dataclass(frozen=True)
class RenderedNote:
    path: str
    content: str
    title: str
    attachment_path: str


@dataclass(frozen=True)
class Capture:
    id: str
    chat_id: int
    source_type: str
    original_name: str
    mime_type: str
    staged_path: str
    attachment_path: str
    note_path: str
    content_sha256: str
    extracted_text: str
    analysis_json: str
    status: str
    created_at: datetime
    expires_at: datetime
