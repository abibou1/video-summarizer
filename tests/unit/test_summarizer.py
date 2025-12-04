# tests/unit/test_summarizer.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config.config import Config
from src.services.summarizer import SummaryBundle, TranscriptSummarizer


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    """Create a test configuration."""
    state_file = tmp_path / "state.json"
    return Config(
        youtube_api_key="key",
        youtube_channel_handle="@handle",
        openai_api_key="openai",
        downloads_dir=tmp_path / "downloads",
        state_file=state_file,
        summary_model="test-model",
        hf_token="test-token",
    )


@patch("src.services.summarizer.InferenceClient")
def test_generate_summaries_parses_json(
    mock_client_class,
    config: Config,
) -> None:
    """Test that generate_summaries correctly parses JSON response."""
    payload: SummaryBundle = {
        "short_summary": "Brief",
        "comprehensive_summary": "Detailed paragraph.",
    }

    # Mock InferenceClient
    mock_client = MagicMock()
    mock_client.text_generation.return_value = json.dumps(payload)
    mock_client_class.return_value = mock_client

    summarizer = TranscriptSummarizer(config=config)
    result = summarizer.generate_summaries("hello world")

    assert result == payload
    assert mock_client_class.called
    assert mock_client.text_generation.called


@patch("src.services.summarizer.InferenceClient")
def test_generate_summaries_rejects_empty_input(
    mock_client_class,
    config: Config,
) -> None:
    """Test that generate_summaries rejects empty input."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    summarizer = TranscriptSummarizer(config=config)
    with pytest.raises(ValueError, match="empty"):
        summarizer.generate_summaries("   ")


@patch("src.services.summarizer.InferenceClient")
def test_client_initialization_caches_instance(
    mock_client_class,
    config: Config,
) -> None:
    """Test that InferenceClient is cached after first initialization."""
    payload: SummaryBundle = {
        "short_summary": "Brief",
        "comprehensive_summary": "Detailed paragraph.",
    }

    mock_client = MagicMock()
    mock_client.text_generation.return_value = json.dumps(payload)
    mock_client_class.return_value = mock_client

    summarizer = TranscriptSummarizer(config=config)

    # First call - should initialize client
    summarizer.generate_summaries("first call")
    call_count_1 = mock_client_class.call_count

    # Second call - should use cached client
    summarizer.generate_summaries("second call")
    call_count_2 = mock_client_class.call_count

    # Should only be called once (cached)
    assert call_count_1 == call_count_2 == 1


@patch("src.services.summarizer.InferenceClient")
def test_raises_error_when_hf_token_missing(
    mock_client_class,
    tmp_path: Path,
) -> None:
    """Test that error is raised when HF_TOKEN is not provided."""
    config = Config(
        youtube_api_key="key",
        youtube_channel_handle="@handle",
        openai_api_key="openai",
        downloads_dir=tmp_path / "downloads",
        state_file=tmp_path / "state.json",
        summary_model="test-model",
        hf_token=None,
    )

    summarizer = TranscriptSummarizer(config=config)
    with pytest.raises(ValueError, match="HF_TOKEN is required"):
        summarizer.generate_summaries("test transcript")
