import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from .models import SourceType
from .security import safe_filename, validate_file_header


@dataclass(frozen=True)
class StagedFile:
    path: Path
    original_name: str
    mime_type: str
    source_type: SourceType
    size: int
    sha256: str


class TelegramFileStager:
    def __init__(self, bot, *, max_pdf_bytes: int, max_audio_bytes: int) -> None:
        self.bot = bot
        self.max_pdf_bytes = max_pdf_bytes
        self.max_audio_bytes = max_audio_bytes

    async def download(self, document_or_voice, destination_dir: Path) -> StagedFile:
        source_type, original_name, mime_type, file_size = self._metadata(document_or_voice)
        limit = self.max_pdf_bytes if source_type is SourceType.PDF else self.max_audio_bytes
        if file_size is not None and file_size > limit:
            raise ValueError("file size exceeds configured limit")

        destination_dir.mkdir(parents=True, exist_ok=True)
        safe_name = safe_filename(original_name, f"capture-{uuid.uuid4().hex[:12]}")
        path = destination_dir / f"{uuid.uuid4().hex[:12]}-{safe_name}"
        try:
            telegram_file = await self.bot.get_file(document_or_voice.file_id)
            await telegram_file.download_to_drive(str(path))
            size = path.stat().st_size
            if size > limit:
                raise ValueError("file size exceeds configured limit")
            validate_file_header(path, source_type)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return StagedFile(path, original_name, mime_type, source_type, size, digest)
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _metadata(document_or_voice):
        mime_type = getattr(document_or_voice, "mime_type", "") or ""
        file_name = getattr(document_or_voice, "file_name", None)
        if file_name or mime_type == "application/pdf":
            return SourceType.PDF, file_name or "capture.pdf", mime_type or "application/pdf", getattr(document_or_voice, "file_size", None)
        unique_id = getattr(document_or_voice, "file_unique_id", document_or_voice.file_id)
        return SourceType.VOICE, f"voice-{unique_id}.ogg", mime_type or "audio/ogg", getattr(document_or_voice, "file_size", None)
