# tests/unit/test_summarizer.py
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.config import Config
from src.services.summarizer import SummaryBundle, TranscriptSummarizer


class _FakeChoice:
    def __init__(self, content: str):
        self.message = SimpleNamespace(content=content)


class _FakeChat:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.last_kwargs = None

    def completions(self) -> None:  # pragma: no cover - placeholder
        raise NotImplementedError

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(choices=[_FakeChoice(self._response_text)])


class _FakeClient:
    def __init__(self, response_payload: SummaryBundle):
        response_text = json.dumps(response_payload)
        self.chat = SimpleNamespace(completions=_FakeChat(response_text))


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    state_file = tmp_path / "state.json"
    return Config(
        youtube_api_key="key",
        youtube_channel_handle="@handle",
        openai_api_key="openai",
        downloads_dir=tmp_path / "downloads",
        state_file=state_file,
    )


def test_generate_summaries_parses_json(config: Config) -> None:
    payload: SummaryBundle = {
        "short_summary": "Brief",
        "comprehensive_summary": "Detailed paragraph.",
    }
    summarizer = TranscriptSummarizer(config=config, client=_FakeClient(payload))
    result = summarizer.generate_summaries("hello world")
    assert result == payload


def test_generate_summaries_rejects_empty_input(config: Config) -> None:
    payload: SummaryBundle = {
        "short_summary": "a",
        "comprehensive_summary": "b",
    }
    summarizer = TranscriptSummarizer(config=config, client=_FakeClient(payload))
    with pytest.raises(ValueError):
        summarizer.generate_summaries("   ")

