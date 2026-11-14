from pathlib import Path

import httpx
import pytest

from telegram_obsidian_agent.extractors import PdfTextExtractor, TranscriptionClient


class FakePage:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self) -> str:
        return self.text


class FakeReader:
    def __init__(self, path: str):
        self.pages = [FakePage("first page"), FakePage("second page")]


def test_pdf_extractor_limits_pages_and_characters(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF")
    extractor = PdfTextExtractor(max_pages=1, max_chars=5, reader_factory=FakeReader)

    result = extractor.extract(source)

    assert result.text == "first"
    assert result.truncated is True


def test_pdf_extractor_reports_empty_text(tmp_path: Path) -> None:
    source = tmp_path / "scan.pdf"
    source.write_bytes(b"%PDF")

    class EmptyReader:
        pages = [FakePage("")]

    result = PdfTextExtractor(max_pages=10, max_chars=100, reader_factory=lambda _: EmptyReader()).extract(source)

    assert result.text == ""
    assert result.truncated is False


def test_transcription_posts_multipart_audio_and_reads_text(tmp_path: Path) -> None:
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"OggS audio")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, json={"text": "transcribed voice"})

    client = TranscriptionClient(
        base_url="https://transcriber.test/v1",
        api_key="secret",
        model="whisper-test",
        transport=httpx.MockTransport(handler),
    )

    assert client.transcribe(source, "audio/ogg") == "transcribed voice"
    assert seen["authorization"] == "Bearer secret"
    assert b'name="model"' in seen["body"]
    assert b"whisper-test" in seen["body"]
    assert b"name=\"file\"" in seen["body"]


def test_transcription_rejects_malformed_provider_response(tmp_path: Path) -> None:
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"OggS audio")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"text": 3}))
    client = TranscriptionClient(
        base_url="https://transcriber.test/v1",
        api_key="secret",
        model="whisper-test",
        transport=transport,
    )

    with pytest.raises(RuntimeError, match="transcription response"):
        client.transcribe(source, "audio/ogg")


def test_transcription_redacts_provider_error(tmp_path: Path) -> None:
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"OggS audio")
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="secret provider details"))
    client = TranscriptionClient(
        base_url="https://transcriber.test/v1",
        api_key="secret",
        model="whisper-test",
        transport=transport,
    )

    with pytest.raises(RuntimeError, match="transcription provider failed") as error:
        client.transcribe(source, "audio/ogg")
    assert "secret provider" not in str(error.value)
