import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest

from telegram_obsidian_agent.models import SourceType
from telegram_obsidian_agent.telegram_files import TelegramFileStager


class FakeDownloadedFile:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def download_to_drive(self, path: str) -> None:
        Path(path).write_bytes(self.payload)


class FakeBot:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.request_count = 0
        self.token = "token"

    async def get_file(self, file_id: str) -> FakeDownloadedFile:
        self.request_count += 1
        return FakeDownloadedFile(self.payload)


class StreamingBot(FakeBot):
    async def get_file(self, file_id: str):
        self.request_count += 1
        return type("StreamingDownloadedFile", (), {"file_path": "https://api.telegram.org/file/bottoken/documents/stream.pdf"})()


class FakeDocument:
    file_id = "file-1"
    file_name = "report.pdf"
    mime_type = "application/pdf"
    file_size = 16


class FakeVoice:
    file_id = "voice-1"
    file_unique_id = "voice-unique"
    mime_type = "audio/ogg"
    file_size = 24


class StreamingFile:
    file_id = "stream-1"
    file_path = "documents/stream.pdf"
    file_name = "stream.pdf"
    mime_type = "application/pdf"
    file_size = None


class AbsoluteStreamingFile(StreamingFile):
    file_path = "https://api.telegram.org/file/bottoken/documents/stream.pdf"


def test_downloads_and_hashes_pdf_into_staging(tmp_path: Path) -> None:
    payload = b"%PDF-1.7\nhello"
    bot = FakeBot(payload)
    stager = TelegramFileStager(bot, max_pdf_bytes=100, max_audio_bytes=100)

    staged = asyncio.run(stager.download(FakeDocument(), tmp_path))

    assert staged.source_type is SourceType.PDF
    assert staged.original_name == "report.pdf"
    assert staged.mime_type == "application/pdf"
    assert staged.size == len(payload)
    assert staged.sha256
    assert staged.path.read_bytes() == payload


def test_rejects_declared_oversize_before_download(tmp_path: Path) -> None:
    bot = FakeBot(b"%PDF")
    stager = TelegramFileStager(bot, max_pdf_bytes=3, max_audio_bytes=100)

    with pytest.raises(ValueError, match="size"):
        asyncio.run(stager.download(FakeDocument(), tmp_path))

    assert bot.request_count == 0


def test_removes_invalid_download(tmp_path: Path) -> None:
    bot = FakeBot(b"not a pdf")
    stager = TelegramFileStager(bot, max_pdf_bytes=100, max_audio_bytes=100)

    with pytest.raises(ValueError, match="PDF"):
        asyncio.run(stager.download(FakeDocument(), tmp_path))

    assert list(tmp_path.iterdir()) == []


def test_voice_without_filename_gets_safe_ogg_name(tmp_path: Path) -> None:
    bot = FakeBot(b"OggS" + b"\x00" * 30)
    stager = TelegramFileStager(bot, max_pdf_bytes=100, max_audio_bytes=100)

    staged = asyncio.run(stager.download(FakeVoice(), tmp_path))

    assert staged.source_type is SourceType.VOICE
    assert staged.original_name == "voice-voice-unique.ogg"


def test_streaming_download_aborts_when_remote_response_exceeds_limit(tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"%PDF-123456"))
    bot = FakeBot(b"unused")
    stager = TelegramFileStager(bot, max_pdf_bytes=5, max_audio_bytes=100, transport=transport)

    with pytest.raises(ValueError, match="size"):
        asyncio.run(stager.download(StreamingFile(), tmp_path))

    assert list(tmp_path.iterdir()) == []


def test_streaming_download_accepts_telegram_absolute_file_url(tmp_path: Path) -> None:
    seen_urls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, content=b"%PDF-1.7\nhello")

    stager = TelegramFileStager(
        StreamingBot(b"unused"),
        max_pdf_bytes=100,
        max_audio_bytes=100,
        transport=httpx.MockTransport(handler),
    )

    staged = asyncio.run(stager.download(AbsoluteStreamingFile(), tmp_path))

    assert staged.path.read_bytes() == b"%PDF-1.7\nhello"
    assert seen_urls == ["https://api.telegram.org/file/bottoken/documents/stream.pdf"]


def test_canonicalizes_media_metadata_after_signature_validation(tmp_path: Path) -> None:
    class MisleadingDocument:
        file_id = "file-2"
        file_name = "voice.ogg"
        mime_type = "application/pdf"
        file_size = 10

    staged = asyncio.run(
        TelegramFileStager(FakeBot(b"%PDF-1.7"), max_pdf_bytes=100, max_audio_bytes=100).download(
            MisleadingDocument(), tmp_path
        )
    )

    assert staged.original_name == "voice.pdf"
    assert staged.mime_type == "application/pdf"
