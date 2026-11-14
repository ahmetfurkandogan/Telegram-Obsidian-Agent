from telegram_obsidian_agent.config import Settings


def valid_environment() -> dict[str, str]:
    return {
        "TELEGRAM_BOT_TOKEN": "bot-token",
        "TELEGRAM_ALLOWED_CHAT_ID": "12345",
        "OBSIDIAN_API_KEY": "obsidian-key",
        "TRANSCRIPTION_API_KEY": "transcription-key",
        "LLM_API_KEY": "llm-key",
    }


def test_settings_load_required_values_and_defaults() -> None:
    settings = Settings.from_env(valid_environment())

    assert settings.telegram_allowed_chat_id == 12345
    assert settings.obsidian_base_url == "http://127.0.0.1:27123"
    assert settings.obsidian_folder == "Telegram Inbox"
    assert settings.transcription_model == "whisper-1"
    assert settings.llm_model == "gpt-4o-mini"
    assert settings.max_pdf_bytes == 20_000_000
    assert settings.max_audio_bytes == 10_000_000
    assert settings.max_pdf_pages == 100
    assert settings.max_extracted_chars == 120_000
    assert settings.pending_ttl_seconds == 900


def test_settings_reject_missing_or_empty_secret() -> None:
    environment = valid_environment()
    del environment["LLM_API_KEY"]

    try:
        Settings.from_env(environment)
    except ValueError as exc:
        assert "LLM_API_KEY" in str(exc)
    else:
        raise AssertionError("missing secret must fail")

    environment = valid_environment()
    environment["LLM_API_KEY"] = ""
    try:
        Settings.from_env(environment)
    except ValueError as exc:
        assert "LLM_API_KEY" in str(exc)
    else:
        raise AssertionError("empty secret must fail")


def test_settings_reject_invalid_chat_id() -> None:
    environment = valid_environment()
    environment["TELEGRAM_ALLOWED_CHAT_ID"] = "not-an-integer"

    try:
        Settings.from_env(environment)
    except ValueError as exc:
        assert "TELEGRAM_ALLOWED_CHAT_ID" in str(exc)
    else:
        raise AssertionError("invalid chat ID must fail")
