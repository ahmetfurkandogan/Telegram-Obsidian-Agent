import asyncio
import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .config import Settings
from .markdown import build_vault_paths, render_note
from .models import Analysis, Capture
from .security import assert_allowed_chat
from .storage import PendingStore
from .telegram_files import TelegramFileStager


logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, *, settings: Settings, store: PendingStore, stager, extractor, transcriber, analyzer, obsidian) -> None:
        self.settings = settings
        self.store = store
        self.stager = stager
        self.extractor = extractor
        self.transcriber = transcriber
        self.analyzer = analyzer
        self.obsidian = obsidian
        self._save_lock = asyncio.Lock()
        self._cleanup_task = None

    def cleanup_expired(self) -> None:
        for staged_path in self.store.expire_and_get_staged_paths(datetime.now(timezone.utc)):
            Path(staged_path).unlink(missing_ok=True)

    def start_cleanup_task(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(max(1, min(60, self.settings.pending_ttl_seconds // 2)))
            self.cleanup_expired()

    async def handle_message(self, update, context=None) -> None:
        chat_id = update.effective_chat.id
        try:
            assert_allowed_chat(chat_id, self.settings.telegram_allowed_chat_id)
        except PermissionError:
            return
        message = update.effective_message
        item = getattr(message, "document", None) or getattr(message, "voice", None)
        if item is None:
            return
        staged = None
        capture = None
        try:
            staged = await self.stager.download(item, self.settings.staging_dir)
            source_type = str(staged.source_type)
            if source_type == "pdf":
                extracted_text = self.extractor.extract(staged.path).text
            else:
                try:
                    extracted_text = self.transcriber.transcribe(staged.path, staged.mime_type)
                except Exception:
                    extracted_text = ""
            analysis = self._analyze(extracted_text, source_type, staged.original_name)
            now = datetime.now(timezone.utc)
            capture_id = uuid.uuid4().hex[:12]
            attachment_path, note_path = build_vault_paths(
                self.settings.obsidian_folder, capture_id, staged.original_name, analysis.title, now
            )
            capture = Capture(
                id=capture_id,
                chat_id=chat_id,
                source_type=source_type,
                original_name=staged.original_name,
                mime_type=staged.mime_type,
                staged_path=str(staged.path),
                attachment_path=attachment_path,
                note_path=note_path,
                content_sha256=staged.sha256,
                extracted_text=extracted_text,
                analysis_json=json.dumps(asdict(analysis), ensure_ascii=False),
                status="pending",
                created_at=now,
                expires_at=now + timedelta(seconds=self.settings.pending_ttl_seconds),
            )
            self.store.create(capture)
            try:
                await self._save_capture(capture.id)
            except Exception as exc:
                logger.error(
                    "capture save failed: %s: %s",
                    type(exc).__name__,
                    str(exc).replace(self.settings.telegram_bot_token, "<redacted>"),
                )
                await message.reply_text("Dosya alındı ancak Obsidian kaydı başarısız oldu. Yerel bekleyen kayıt korunuyor.")
                return
            await message.reply_text(f"Kaydedildi: {analysis.title}")
        except Exception as exc:
            logger.error(
                "message processing failed: %s: %s",
                type(exc).__name__,
                str(exc).replace(self.settings.telegram_bot_token, "<redacted>"),
            )
            if capture is None and staged is not None:
                staged.path.unlink(missing_ok=True)
            try:
                await message.reply_text("İşlenemedi. Dosya türü, boyutu veya sağlayıcı bağlantısını kontrol edin.")
            except Exception:
                pass

    def _analyze(self, extracted_text: str, source_type: str, original_name: str) -> Analysis:
        if not extracted_text.strip():
            return Analysis(
                title=Path(original_name).stem or "Telegram capture",
                summary="No extractable text was available.",
                tags=["telegram-inbox"],
                body=f"Original attachment: {original_name}\n\nText extraction or transcription returned no content.",
            )
        try:
            return self.analyzer.analyze(extracted_text, source_type, original_name)
        except Exception:
            return Analysis(
                title=Path(original_name).stem or "Telegram capture",
                summary="AI analysis unavailable; extracted content preserved.",
                tags=["telegram-inbox"],
                body=extracted_text,
            )

    async def _save_capture(self, capture_id: str) -> None:
        async with self._save_lock:
            capture = self.store.get(capture_id)
            if capture is None or capture.status != "pending":
                raise RuntimeError("capture is not pending")
            now = datetime.now(timezone.utc)
            if capture.expires_at <= now:
                self.store.expire(now)
                Path(capture.staged_path).unlink(missing_ok=True)
                raise RuntimeError("capture expired")
            analysis = Analysis(**json.loads(capture.analysis_json))
            rendered = render_note(analysis, capture, capture.created_at, self.settings.obsidian_folder)
            await asyncio.to_thread(
                self.obsidian.write_attachment,
                rendered,
                Path(capture.staged_path),
                capture.mime_type,
                capture.content_sha256,
            )
            await asyncio.to_thread(self.obsidian.write_note, rendered)
            if self.store.mark_saved(capture_id):
                Path(capture.staged_path).unlink(missing_ok=True)
                return
            raise RuntimeError("capture was saved by another worker")


def build_application(settings: Settings, store: PendingStore, stager, extractor, transcriber, analyzer, obsidian) -> Application:
    application = Application.builder().token(settings.telegram_bot_token).build()
    if stager is None:
        stager = TelegramFileStager(
            application.bot,
            max_pdf_bytes=settings.max_pdf_bytes,
            max_audio_bytes=settings.max_audio_bytes,
        )
    service = BotService(
        settings=settings,
        store=store,
        stager=stager,
        extractor=extractor,
        transcriber=transcriber,
        analyzer=analyzer,
        obsidian=obsidian,
    )

    async def post_init(_application) -> None:
        service.start_cleanup_task()

    async def post_stop(_application) -> None:
        await service.stop_cleanup_task()

    application.post_init = post_init
    application.post_stop = post_stop

    async def start(update, context) -> None:
        try:
            assert_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id)
        except PermissionError:
            return
        await update.effective_message.reply_text("PDF veya ses mesajı gönderin. Dosyalar otomatik kaydedilir.")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.VOICE, service.handle_message))
    return application
