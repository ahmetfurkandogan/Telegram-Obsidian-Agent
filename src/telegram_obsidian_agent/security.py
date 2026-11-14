import re
import unicodedata
from pathlib import Path

from .models import SourceType


def assert_allowed_chat(chat_id: int, allowed_chat_id: int) -> None:
    if chat_id != allowed_chat_id:
        raise PermissionError("chat is not allowed")


def safe_filename(name: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).replace("\\", "/").split("/")[-1]
    stem, dot, suffix = normalized.rpartition(".")
    if not dot or not stem:
        stem, suffix = normalized, ""
    stem = re.sub(r"\s+", "-", stem)
    stem = re.sub(r"[^A-Za-z0-9_-]", "", stem).strip(".-_")
    suffix = re.sub(r"[^A-Za-z0-9]", "", suffix)
    safe = stem or fallback
    if suffix:
        safe = f"{safe}.{suffix}"
    return safe[:120]


def validate_file_header(path: Path, source_type: SourceType) -> None:
    with path.open("rb") as file:
        header = file.read(4)
    if source_type is SourceType.PDF and header != b"%PDF":
        raise ValueError("file is not a valid PDF")
    if source_type is SourceType.VOICE and header != b"OggS":
        raise ValueError("file is not supported audio")
