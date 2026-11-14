from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx


@dataclass(frozen=True)
class ExtractedText:
    text: str
    truncated: bool


def _default_reader(path: Path):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF support requires the pypdf dependency") from exc
    return PdfReader(str(path))


class PdfTextExtractor:
    def __init__(self, *, max_pages: int, max_chars: int, reader_factory: Callable = _default_reader) -> None:
        self.max_pages = max_pages
        self.max_chars = max_chars
        self.reader_factory = reader_factory

    def extract(self, path: Path) -> ExtractedText:
        reader = self.reader_factory(path)
        chunks: list[str] = []
        total = 0
        truncated = False
        for index, page in enumerate(reader.pages):
            if index >= self.max_pages:
                truncated = True
                break
            page_text = page.extract_text() or ""
            if not page_text:
                continue
            remaining = self.max_chars - total
            if remaining <= 0:
                truncated = True
                break
            chunks.append(page_text[:remaining])
            total += min(len(page_text), remaining)
            if len(page_text) > remaining:
                truncated = True
                break
        return ExtractedText("\n\n".join(chunks)[: self.max_chars], truncated)


class TranscriptionClient:
    def __init__(self, *, base_url: str, api_key: str, model: str, transport=None, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.transport = transport
        self.timeout = timeout

    def transcribe(self, path: Path, mime_type: str) -> str:
        try:
            with path.open("rb") as audio, httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.post(
                    "/audio/transcriptions",
                    data={"model": self.model},
                    files={"file": (path.name, audio, mime_type)},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError, OSError) as exc:
            raise RuntimeError("transcription provider failed") from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise RuntimeError("invalid transcription response")
        return text.strip()
