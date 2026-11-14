import json

import httpx
import pytest

from telegram_obsidian_agent.llm import LLMAnalyzer


def response_transport(payload: dict, seen: dict | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    return httpx.MockTransport(handler)


def test_llm_analyzer_validates_and_normalizes_structured_json() -> None:
    seen = {}
    analyzer = LLMAnalyzer(
        base_url="https://llm.test/v1",
        api_key="secret",
        model="test-model",
        transport=response_transport(
            {"title": "A title", "summary": "A summary", "tags": ["Project Notes", "python"], "body": "Full body"},
            seen,
        ),
    )

    result = analyzer.analyze("untrusted source text", "pdf", "report.pdf")

    assert result.title == "A title"
    assert result.tags == ["project-notes", "python"]
    assert result.body == "Full body"
    assert "untrusted source text" in seen["body"]["messages"][1]["content"]


def test_llm_analyzer_rejects_extra_fields() -> None:
    analyzer = LLMAnalyzer(
        base_url="https://llm.test/v1",
        api_key="secret",
        model="test-model",
        transport=response_transport(
            {"title": "A", "summary": "B", "tags": [], "body": "C", "extra": "no"}
        ),
    )

    with pytest.raises(RuntimeError, match="analysis response"):
        analyzer.analyze("text", "voice", "voice.ogg")


def test_llm_analyzer_rejects_oversized_fields() -> None:
    analyzer = LLMAnalyzer(
        base_url="https://llm.test/v1",
        api_key="secret",
        model="test-model",
        transport=response_transport(
            {"title": "A", "summary": "B", "tags": ["ok"], "body": "x" * 12001}
        ),
    )

    with pytest.raises(RuntimeError, match="analysis response"):
        analyzer.analyze("text", "pdf", "report.pdf")


def test_llm_analyzer_redacts_provider_errors() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, text="secret provider detail"))
    analyzer = LLMAnalyzer(base_url="https://llm.test/v1", api_key="secret", model="test-model", transport=transport)

    with pytest.raises(RuntimeError, match="analysis provider failed") as error:
        analyzer.analyze("text", "pdf", "report.pdf")
    assert "secret provider" not in str(error.value)
