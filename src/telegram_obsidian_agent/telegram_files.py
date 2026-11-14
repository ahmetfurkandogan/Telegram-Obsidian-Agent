import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

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
    def __init__(self, bot, *, max_pdf_bytes: int, max_audio_bytes: int, transport=None) -> None:
        self.bot = bot
        self.max_pdf_bytes = max_pdf_bytes
        self.max_audio_bytes = max_audio_bytes
        self.transport = transport

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
            if getattr(telegram_file, "file_path", None):
                url = f"https://api.telegram.org/file/bot{self.bot.token}/{quote(telegram_file.file_path, safe='/')}"
                async with httpx.AsyncClient(transport=self.transport, timeout=60.0) as client:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        size = 0
                        with path.open("wb") as output:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > limit:
                                    raise ValueError("file size exceeds configured limit")
                                output.write(chunk)
            else:
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
        is_pdf = mime_type == "application/pdf" or (file_name and file_name.lower().endswith(".pdf"))
        is_voice = mime_type.startswith("audio/") or not file_name
        if is_pdf:
            stem = safe_filename(file_name or "capture", "capture").rsplit(".", 1)[0]
            return SourceType.PDF, f"{stem}.pdf", "application/pdf", getattr(document_or_voice, "file_size", None)
        if not is_voice:
            raise ValueError("unsupported media type")
        unique_id = getattr(document_or_voice, "file_unique_id", document_or_voice.file_id)
        return SourceType.VOICE, f"voice-{unique_id}.ogg", "audio/ogg", getattr(document_or_voice, "file_size", None)
