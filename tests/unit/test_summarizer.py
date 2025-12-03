# tests/unit/test_summarizer.py
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import torch

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
        use_quantization=False,
        device="cpu",
    )


@pytest.fixture()
def mock_model_and_tokenizer():
    """Create mock model and tokenizer for testing."""
    # Mock tokenizer
    mock_tokenizer = MagicMock()
    mock_tokenizer.pad_token = "<pad>"
    mock_tokenizer.eos_token = "</s>"
    mock_tokenizer.pad_token_id = 0
    mock_tokenizer.eos_token_id = 1

    def tokenize_side_effect(text, **kwargs):
        # Return a simple tensor representation
        tokens = [1, 2, 3, 4, 5]  # Mock token IDs
        return {"input_ids": torch.tensor([tokens]), "attention_mask": torch.tensor([[1] * len(tokens)])}

    mock_tokenizer.side_effect = tokenize_side_effect
    mock_tokenizer.decode = MagicMock(return_value='{"short_summary": "Brief", "comprehensive_summary": "Detailed paragraph."}')

    # Mock model
    mock_model = MagicMock()
    # Mock generate to return tensor with input + generated tokens
    mock_model.generate = MagicMock(return_value=torch.tensor([[1, 2, 3, 4, 5, 10, 11, 12]]))
    mock_model.parameters.return_value = [torch.tensor([1.0])]  # For device detection
    mock_model.eval = MagicMock(return_value=mock_model)

    return mock_model, mock_tokenizer


@patch("src.services.summarizer.AutoModelForCausalLM")
@patch("src.services.summarizer.AutoTokenizer")
def test_generate_summaries_parses_json(
    mock_tokenizer_class,
    mock_model_class,
    config: Config,
    mock_model_and_tokenizer,
) -> None:
    """Test that generate_summaries correctly parses JSON response."""
    mock_model, mock_tokenizer = mock_model_and_tokenizer

    # Setup mocks
    mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
    mock_model_class.from_pretrained.return_value = mock_model

    payload: SummaryBundle = {
        "short_summary": "Brief",
        "comprehensive_summary": "Detailed paragraph.",
    }

    # Mock decode to return JSON
    mock_tokenizer.decode.return_value = json.dumps(payload)

    summarizer = TranscriptSummarizer(config=config)
    result = summarizer.generate_summaries("hello world")

    assert result == payload
    assert mock_model_class.from_pretrained.called
    assert mock_tokenizer_class.from_pretrained.called


@patch("src.services.summarizer.AutoModelForCausalLM")
@patch("src.services.summarizer.AutoTokenizer")
def test_generate_summaries_rejects_empty_input(
    mock_tokenizer_class,
    mock_model_class,
    config: Config,
    mock_model_and_tokenizer,
) -> None:
    """Test that generate_summaries rejects empty input."""
    mock_model, mock_tokenizer = mock_model_and_tokenizer

    # Setup mocks
    mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
    mock_model_class.from_pretrained.return_value = mock_model

    summarizer = TranscriptSummarizer(config=config)
    with pytest.raises(ValueError, match="empty"):
        summarizer.generate_summaries("   ")


@patch("src.services.summarizer.AutoModelForCausalLM")
@patch("src.services.summarizer.AutoTokenizer")
def test_model_loading_caches_instances(
    mock_tokenizer_class,
    mock_model_class,
    config: Config,
    mock_model_and_tokenizer,
) -> None:
    """Test that model and tokenizer are cached after first load."""
    mock_model, mock_tokenizer = mock_model_and_tokenizer

    # Setup mocks
    mock_tokenizer_class.from_pretrained.return_value = mock_tokenizer
    mock_model_class.from_pretrained.return_value = mock_model

    payload: SummaryBundle = {
        "short_summary": "Brief",
        "comprehensive_summary": "Detailed paragraph.",
    }
    mock_tokenizer.decode.return_value = json.dumps(payload)

    summarizer = TranscriptSummarizer(config=config)

    # First call - should load model
    summarizer.generate_summaries("first call")
    call_count_1 = mock_model_class.from_pretrained.call_count

    # Second call - should use cached model
    summarizer.generate_summaries("second call")
    call_count_2 = mock_model_class.from_pretrained.call_count

    # Should only be called once (cached)
    assert call_count_1 == call_count_2 == 1
