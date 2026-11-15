import importlib
from pathlib import Path

import pytest

from telegram_obsidian_agent.config import Settings
from telegram_obsidian_agent.main import load_settings


def environment() -> dict[str, str]:
    return {
        "TELEGRAM_BOT_TOKEN": "token",
        "TELEGRAM_ALLOWED_CHAT_ID": "123",
        "OBSIDIAN_API_KEY": "obsidian",
        "TRANSCRIPTION_API_KEY": "transcription",
        "LLM_API_KEY": "llm",
    }


def test_load_settings_reads_environment(monkeypatch) -> None:
    values = environment()
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    settings = load_settings()

    assert isinstance(settings, Settings)
    assert settings.telegram_allowed_chat_id == 123


def test_load_settings_rejects_missing_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("telegram_obsidian_agent.main.load_dotenv", lambda *args, **kwargs: None)
    for key in environment():
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        load_settings()


def test_import_does_not_start_polling(monkeypatch) -> None:
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("telegram.ext.Application.run_polling", fail_if_called)
    importlib.import_module("telegram_obsidian_agent.main")

    assert called is False
