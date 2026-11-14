import hashlib
from pathlib import Path

import httpx
import pytest

from telegram_obsidian_agent.models import RenderedNote
from telegram_obsidian_agent.obsidian import ObsidianClient


def test_writes_attachment_create_only_and_reuses_matching_conflict(tmp_path: Path) -> None:
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"OggS audio")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "PUT":
            return httpx.Response(412)
        return httpx.Response(200, content=source.read_bytes())

    client = ObsidianClient(
        base_url="http://obsidian.test",
        api_key="secret",
        transport=httpx.MockTransport(handler),
    )
    note = RenderedNote("Telegram Inbox/note.md", "note", "Title", "Telegram Inbox/voice file.ogg")

    client.write_attachment(note, source, "audio/ogg", hashlib.sha256(source.read_bytes()).hexdigest())

    assert seen[0].method == "PUT"
    assert seen[0].url.raw_path.decode() == "/vault/Telegram%20Inbox/voice%20file.ogg"
    assert seen[0].headers["authorization"] == "Bearer secret"
    assert seen[0].headers["if-none-match"] == "*"
    assert seen[0].headers["content-type"] == "audio/ogg"
    assert seen[1].method == "GET"


def test_rejects_conflict_with_different_attachment_content(tmp_path: Path) -> None:
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"OggS audio")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(412) if request.method == "PUT" else httpx.Response(200, content=b"different")
    )
    client = ObsidianClient(base_url="http://obsidian.test", api_key="secret", transport=transport)

    with pytest.raises(FileExistsError, match="different content"):
        client.write_attachment(
            RenderedNote("note.md", "note", "Title", "Telegram Inbox/voice.ogg"),
            source,
            "audio/ogg",
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )


def test_writes_markdown_with_expected_headers() -> None:
    seen = []
    transport = httpx.MockTransport(lambda request: seen.append(request) or httpx.Response(204))
    client = ObsidianClient(base_url="http://obsidian.test", api_key="secret", transport=transport)

    client.write_note(RenderedNote("Telegram Inbox/note.md", "markdown", "Title", "file.pdf"))

    request = seen[0]
    assert request.method == "PUT"
    assert request.url.raw_path.decode() == "/vault/Telegram%20Inbox/note.md"
    assert request.headers["if-none-match"] == "*"
    assert request.headers["content-type"] == "text/markdown"
    assert request.content == b"markdown"


def test_redacts_api_key_from_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="secret provider detail"))
    client = ObsidianClient(base_url="http://obsidian.test", api_key="secret", transport=transport)

    with pytest.raises(RuntimeError, match="Obsidian write failed") as error:
        client.write_note(RenderedNote("note.md", "markdown", "Title", "file.pdf"))
    assert "secret" not in str(error.value)
