from pathlib import Path

import pytest

from telegram_obsidian_agent.models import SourceType
from telegram_obsidian_agent.security import (
    assert_allowed_chat,
    safe_filename,
    validate_file_header,
)


def test_rejects_chat_id_that_is_not_allowlisted() -> None:
    with pytest.raises(PermissionError):
        assert_allowed_chat(7, 8)


def test_safe_filename_removes_traversal_and_control_characters() -> None:
    assert safe_filename("../../bad\nname?.pdf", "capture") == "bad-name.pdf"
    assert safe_filename("", "capture") == "capture"


def test_accepts_pdf_signature_and_rejects_other_content(tmp_path: Path) -> None:
    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncontent")
    validate_file_header(pdf, SourceType.PDF)

    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not a pdf")
    with pytest.raises(ValueError, match="PDF"):
        validate_file_header(invalid, SourceType.PDF)


def test_accepts_ogg_signature_and_rejects_other_audio(tmp_path: Path) -> None:
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"OggS" + b"\x00" * 20)
    validate_file_header(audio, SourceType.VOICE)

    invalid = tmp_path / "invalid.ogg"
    invalid.write_bytes(b"not audio")
    with pytest.raises(ValueError, match="audio"):
        validate_file_header(invalid, SourceType.VOICE)
