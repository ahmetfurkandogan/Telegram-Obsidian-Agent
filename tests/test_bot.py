import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from telegram_obsidian_agent.bot import BotService
from telegram_obsidian_agent.config import Settings
from telegram_obsidian_agent.extractors import ExtractedText
from telegram_obsidian_agent.models import Analysis
from telegram_obsidian_agent.storage import PendingStore
from telegram_obsidian_agent.telegram_files import StagedFile


def settings(tmp_path: Path, *, ttl: int = 900) -> Settings:
    return Settings(
        telegram_bot_token="token",
        telegram_allowed_chat_id=123,
        obsidian_api_key="obsidian",
        transcription_api_key="transcription",
        llm_api_key="llm",
        obsidian_base_url="http://obsidian.test",
        obsidian_folder="Telegram Inbox",
        transcription_base_url="http://transcriber.test/v1",
        transcription_model="whisper",
        llm_base_url="http://llm.test/v1",
        llm_model="model",
        database_path=tmp_path / "agent.sqlite3",
        staging_dir=tmp_path / "staging",
        max_pdf_bytes=1000,
        max_audio_bytes=1000,
        max_pdf_pages=10,
        max_extracted_chars=1000,
        pending_ttl_seconds=ttl,
    )


class FakeMessage:
    def __init__(self, *, document=None, voice=None):
        self.document = document
        self.voice = voice
        self.replies = []

    async def reply_text(self, text, reply_markup=None):
        self.replies.append((text, reply_markup))


class FakeChat:
    def __init__(self, chat_id: int):
        self.id = chat_id


class FakeUpdate:
    def __init__(self, chat_id: int, message: FakeMessage):
        self.effective_chat = FakeChat(chat_id)
        self.effective_message = message
        self.callback_query = None


class FakeCallback:
    def __init__(self, data: str):
        self.data = data
        self.answers = []

    async def answer(self, text=None):
        self.answers.append(text)


class FakeCallbackUpdate:
    def __init__(self, chat_id: int, data: str):
        self.effective_chat = FakeChat(chat_id)
        self.callback_query = FakeCallback(data)


class FakeStager:
    def __init__(self, tmp_path: Path, source_type: str):
        self.tmp_path = tmp_path
        self.source_type = source_type

    async def download(self, item, destination_dir: Path) -> StagedFile:
        destination_dir.mkdir(parents=True, exist_ok=True)
        path = destination_dir / ("report.pdf" if self.source_type == "pdf" else "voice.ogg")
        path.write_bytes(b"%PDF content" if self.source_type == "pdf" else b"OggS audio")
        return StagedFile(path, path.name, "application/pdf" if self.source_type == "pdf" else "audio/ogg", self.source_type, path.stat().st_size, "hash")


class FakeExtractor:
    def extract(self, path: Path) -> ExtractedText:
        return ExtractedText("extracted pdf text", False)


class FakeTranscriber:
    def transcribe(self, path: Path, mime_type: str) -> str:
        return "transcribed voice text"


class FakeAnalyzer:
    def __init__(self, body: str = "generated body"):
        self.body = body

    def analyze(self, text: str, source_type: str, original_name: str) -> Analysis:
        return Analysis("Generated title", "Generated summary", ["telegram"], self.body)


class FakeObsidian:
    def __init__(self):
        self.attachment_calls = 0
        self.note_calls = 0
        self.fail_note_once = False

    def write_attachment(self, note, source_path, mime_type, sha256):
        self.attachment_calls += 1

    def write_note(self, note):
        self.note_calls += 1
        if self.fail_note_once:
            self.fail_note_once = False
            raise RuntimeError("temporary write failure")


def make_service(tmp_path: Path, source_type: str = "pdf", *, ttl: int = 900, body: str = "generated body"):
    config = settings(tmp_path, ttl=ttl)
    obsidian = FakeObsidian()
    service = BotService(
        settings=config,
        store=PendingStore(config.database_path),
        stager=FakeStager(tmp_path, source_type),
        extractor=FakeExtractor(),
        transcriber=FakeTranscriber(),
        analyzer=FakeAnalyzer(body),
        obsidian=obsidian,
    )
    return service, obsidian


def test_pdf_message_creates_preview_with_save_and_cancel_buttons(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    message = FakeMessage(document=object())

    asyncio.run(service.handle_message(FakeUpdate(123, message)))

    assert len(message.replies) == 1
    text, keyboard = message.replies[0]
    assert "Generated title" in text
    assert "Kaydet" in str(keyboard)
    assert "İptal" in str(keyboard)


def test_voice_message_routes_to_transcription(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path, source_type="voice")
    message = FakeMessage(voice=object())

    asyncio.run(service.handle_message(FakeUpdate(123, message)))

    assert "Generated summary" in message.replies[0][0]


def test_unauthorized_chat_is_ignored(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path)
    message = FakeMessage(document=object())

    asyncio.run(service.handle_message(FakeUpdate(999, message)))

    assert message.replies == []


def test_preview_is_truncated_for_telegram(tmp_path: Path) -> None:
    service, _ = make_service(tmp_path, body="x" * 12000)
    message = FakeMessage(document=object())

    asyncio.run(service.handle_message(FakeUpdate(123, message)))

    assert len(message.replies[0][0]) <= 3500
    assert "truncated" in message.replies[0][0].lower()


def test_save_callback_writes_once_and_repeated_callback_is_harmless(tmp_path: Path) -> None:
    service, obsidian = make_service(tmp_path)
    message = FakeMessage(document=object())
    asyncio.run(service.handle_message(FakeUpdate(123, message)))
    callback_data = message.replies[0][1].inline_keyboard[0][0].callback_data

    first = FakeCallbackUpdate(123, callback_data)
    second = FakeCallbackUpdate(123, callback_data)
    asyncio.run(service.handle_callback(first))
    asyncio.run(service.handle_callback(second))

    assert obsidian.attachment_calls == 1
    assert obsidian.note_calls == 1


def test_cancel_callback_prevents_writes(tmp_path: Path) -> None:
    service, obsidian = make_service(tmp_path)
    message = FakeMessage(document=object())
    asyncio.run(service.handle_message(FakeUpdate(123, message)))
    callback_data = message.replies[0][1].inline_keyboard[0][1].callback_data

    asyncio.run(service.handle_callback(FakeCallbackUpdate(123, callback_data)))

    assert obsidian.attachment_calls == 0
    assert obsidian.note_calls == 0


def test_expired_capture_does_not_write(tmp_path: Path) -> None:
    service, obsidian = make_service(tmp_path, ttl=0)
    message = FakeMessage(document=object())
    asyncio.run(service.handle_message(FakeUpdate(123, message)))
    callback_data = message.replies[0][1].inline_keyboard[0][0].callback_data

    asyncio.run(service.handle_callback(FakeCallbackUpdate(123, callback_data)))

    assert obsidian.note_calls == 0


def test_failed_note_write_keeps_capture_retryable(tmp_path: Path) -> None:
    service, obsidian = make_service(tmp_path)
    obsidian.fail_note_once = True
    message = FakeMessage(document=object())
    asyncio.run(service.handle_message(FakeUpdate(123, message)))
    callback_data = message.replies[0][1].inline_keyboard[0][0].callback_data

    asyncio.run(service.handle_callback(FakeCallbackUpdate(123, callback_data)))
    asyncio.run(service.handle_callback(FakeCallbackUpdate(123, callback_data)))

    assert obsidian.attachment_calls == 2
    assert obsidian.note_calls == 2
