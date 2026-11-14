import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .config import Settings
from .markdown import build_vault_paths, preview_text, render_note
from .models import Analysis, Capture
from .security import assert_allowed_chat
from .storage import PendingStore
from .telegram_files import TelegramFileStager


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

    async def handle_message(self, update) -> None:
        chat_id = update.effective_chat.id
        try:
            assert_allowed_chat(chat_id, self.settings.telegram_allowed_chat_id)
        except PermissionError:
            return
        message = update.effective_message
        item = getattr(message, "document", None) or getattr(message, "voice", None)
        if item is None:
            return
        try:
            staged = await self.stager.download(item, self.settings.staging_dir)
            source_type = str(staged.source_type)
            if source_type == "pdf":
                extracted_text = self.extractor.extract(staged.path).text
            else:
                extracted_text = self.transcriber.transcribe(staged.path, staged.mime_type)
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
            rendered = render_note(analysis, capture, now, self.settings.obsidian_folder)
            self.store.create(capture)
            keyboard = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("Kaydet", callback_data=f"save:{capture_id}"),
                    InlineKeyboardButton("İptal", callback_data=f"cancel:{capture_id}"),
                ]]
            )
            await message.reply_text(preview_text(rendered, 3500), reply_markup=keyboard)
        except Exception:
            staged_path = locals().get("staged")
            if staged_path is not None:
                staged_path.path.unlink(missing_ok=True)
            await message.reply_text("İşlenemedi. Dosya türü, boyutu veya sağlayıcı bağlantısını kontrol edin.")

    def _analyze(self, extracted_text: str, source_type: str, original_name: str) -> Analysis:
        if extracted_text.strip():
            return self.analyzer.analyze(extracted_text, source_type, original_name)
        return Analysis(
            title=Path(original_name).stem or "Telegram capture",
            summary="No extractable text was available.",
            tags=["telegram-inbox"],
            body=f"Original attachment: {original_name}\n\nText extraction or transcription returned no content.",
        )

    async def handle_callback(self, update) -> None:
        chat_id = update.effective_chat.id
        query = update.callback_query
        try:
            assert_allowed_chat(chat_id, self.settings.telegram_allowed_chat_id)
        except PermissionError:
            return
        try:
            action, capture_id = query.data.split(":", 1)
        except ValueError:
            await query.answer("Geçersiz işlem")
            return
        capture = self.store.get(capture_id)
        if capture is None:
            await query.answer("Kayıt bulunamadı")
            return
        if action == "cancel":
            if self.store.mark_cancelled(capture_id):
                Path(capture.staged_path).unlink(missing_ok=True)
                await query.answer("İptal edildi")
            else:
                await query.answer("Kayıt zaten işlendi")
            return
        if action != "save":
            await query.answer("Geçersiz işlem")
            return
        async with self._save_lock:
            capture = self.store.get(capture_id)
            if capture is None or capture.status != "pending":
                await query.answer("Kayıt zaten işlendi")
                return
            now = datetime.now(timezone.utc)
            if capture.expires_at <= now:
                self.store.expire(now)
                Path(capture.staged_path).unlink(missing_ok=True)
                await query.answer("Önizleme süresi doldu")
                return
            try:
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
            except Exception:
                await query.answer("Kaydedilemedi. Tekrar deneyin.")
                return
            if self.store.mark_saved(capture_id):
                Path(capture.staged_path).unlink(missing_ok=True)
                await query.answer("Kaydedildi")
            else:
                await query.answer("Kayıt zaten işlendi")


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

    async def start(update, context) -> None:
        try:
            assert_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id)
        except PermissionError:
            return
        await update.effective_message.reply_text("PDF veya ses mesajı gönderin. Önizlemeden sonra Kaydet seçin.")

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL | filters.VOICE, service.handle_message))
    application.add_handler(CallbackQueryHandler(service.handle_callback, pattern=r"^(save|cancel):[A-Za-z0-9]+$"))
    return application
