from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _integer(environ: Mapping[str, str], name: str, default: int | None = None) -> int:
    raw = environ.get(name)
    if raw is None and default is not None:
        return default
    if raw is None:
        raise ValueError(f"{name} is required")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_allowed_chat_id: int
    obsidian_api_key: str
    transcription_api_key: str
    llm_api_key: str
    obsidian_base_url: str
    obsidian_folder: str
    transcription_base_url: str
    transcription_model: str
    llm_base_url: str
    llm_model: str
    database_path: Path
    staging_dir: Path
    max_pdf_bytes: int
    max_audio_bytes: int
    max_pdf_pages: int
    max_extracted_chars: int
    pending_ttl_seconds: int

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        return cls(
            telegram_bot_token=_required(environ, "TELEGRAM_BOT_TOKEN"),
            telegram_allowed_chat_id=_integer(environ, "TELEGRAM_ALLOWED_CHAT_ID"),
            obsidian_api_key=_required(environ, "OBSIDIAN_API_KEY"),
            transcription_api_key=_required(environ, "TRANSCRIPTION_API_KEY"),
            llm_api_key=_required(environ, "LLM_API_KEY"),
            obsidian_base_url=environ.get("OBSIDIAN_BASE_URL", "http://127.0.0.1:27123").rstrip("/"),
            obsidian_folder=environ.get("OBSIDIAN_FOLDER", "Telegram Inbox").strip("/"),
            transcription_base_url=environ.get("TRANSCRIPTION_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            transcription_model=environ.get("TRANSCRIPTION_MODEL", "whisper-1"),
            llm_base_url=environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            llm_model=environ.get("LLM_MODEL", "gpt-4o-mini"),
            database_path=Path(environ.get("DATABASE_PATH", "data/agent.sqlite3")),
            staging_dir=Path(environ.get("STAGING_DIR", "data/staging")),
            max_pdf_bytes=_integer(environ, "MAX_PDF_BYTES", 20_000_000),
            max_audio_bytes=_integer(environ, "MAX_AUDIO_BYTES", 10_000_000),
            max_pdf_pages=_integer(environ, "MAX_PDF_PAGES", 100),
            max_extracted_chars=_integer(environ, "MAX_EXTRACTED_CHARS", 120_000),
            pending_ttl_seconds=_integer(environ, "PENDING_TTL_SECONDS", 900),
        )
