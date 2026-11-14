import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from .bot import build_application
from .config import Settings
from .extractors import PdfTextExtractor, TranscriptionClient
from .llm import LLMAnalyzer
from .obsidian import ObsidianClient
from .storage import PendingStore


def load_settings() -> Settings:
    load_dotenv()
    return Settings.from_env(os.environ)


def create_application(settings: Settings):
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    store = PendingStore(settings.database_path)
    now = datetime.now(timezone.utc)
    store.expire(now)
    store.purge(now - timedelta(days=30))
    for path in settings.staging_dir.iterdir():
        if path.is_file() and path.stat().st_mtime < (now - timedelta(seconds=settings.pending_ttl_seconds)).timestamp():
            path.unlink(missing_ok=True)
    extractor = PdfTextExtractor(max_pages=settings.max_pdf_pages, max_chars=settings.max_extracted_chars)
    transcriber = TranscriptionClient(
        base_url=settings.transcription_base_url,
        api_key=settings.transcription_api_key,
        model=settings.transcription_model,
    )
    analyzer = LLMAnalyzer(base_url=settings.llm_base_url, api_key=settings.llm_api_key, model=settings.llm_model)
    obsidian = ObsidianClient(base_url=settings.obsidian_base_url, api_key=settings.obsidian_api_key)
    return build_application(settings, store, None, extractor, transcriber, analyzer, obsidian)


def run() -> None:
    settings = load_settings()
    application = create_application(settings)
    application.run_polling()


if __name__ == "__main__":
    run()
