import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

from .models import RenderedNote


class ObsidianClient:
    def __init__(self, *, base_url: str, api_key: str, transport=None, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport
        self.timeout = timeout

    def write_attachment(self, note: RenderedNote, source_path: Path, mime_type: str, sha256: str) -> None:
        path = self._vault_url(note.attachment_path)
        try:
            with source_path.open("rb") as source, httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.put(
                    path,
                    content=source,
                    headers={"Content-Type": mime_type, "If-None-Match": "*"},
                )
                if response.status_code in (409, 412):
                    existing = client.get(path)
                    if existing.is_success and hashlib.sha256(existing.content).hexdigest() == sha256:
                        return
                    raise FileExistsError("attachment exists with different content")
                response.raise_for_status()
        except FileExistsError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise RuntimeError("Obsidian write failed") from exc

    def write_note(self, note: RenderedNote) -> None:
        path = self._vault_url(note.path)
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.put(
                    path,
                    content=note.content.encode("utf-8"),
                    headers={"Content-Type": "text/markdown", "If-None-Match": "*"},
                )
                if response.status_code in (409, 412):
                    raise FileExistsError("note path already exists")
                response.raise_for_status()
        except FileExistsError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise RuntimeError("Obsidian write failed") from exc

    def healthcheck(self) -> None:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                client.get("/").raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("Obsidian healthcheck failed") from exc

    @staticmethod
    def _vault_url(path: str) -> str:
        pure = PurePosixPath(path)
        if pure.is_absolute() or not path or ".." in pure.parts:
            raise ValueError("vault path must be relative")
        return "/vault/" + quote(str(pure), safe="/")
