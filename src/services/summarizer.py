# src/services/summarizer.py
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, TypedDict

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)

from config.config import Config

LOGGER = logging.getLogger(__name__)


class SummaryBundle(TypedDict):
    """Container for short and comprehensive summaries."""

    short_summary: str
    comprehensive_summary: str


@dataclass
class TranscriptSummarizer:
    """Generate multi-length summaries for saved transcripts using Hugging Face models."""

    config: Config
    _model: Optional[AutoModelForCausalLM] = None
    _tokenizer: Optional[AutoTokenizer] = None

    def __post_init__(self) -> None:
        """Initialize model and tokenizer lazily on first use."""
        # Model will be loaded on first call to generate_summaries
        pass

    def _load_model(self) -> tuple[AutoModelForCausalLM, AutoTokenizer]:
        """Load the Hugging Face model and tokenizer.

        Returns:
            Tuple of (model, tokenizer) loaded from Hugging Face.

        Raises:
            ValueError: If model loading fails or HF token is missing when required.
        """
        if self._model is not None and self._tokenizer is not None:
            return self._model, self._tokenizer

        LOGGER.info("Loading model: %s", self.config.summary_model)

        # Check if HF token is required (Llama models require authentication)
        if not self.config.hf_token:
            LOGGER.warning(
                "HF_TOKEN not set. Some models may require authentication. "
                "Set HF_TOKEN environment variable if authentication fails."
            )

        # Determine device
        if self.config.device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = self.config.device

        LOGGER.info("Using device: %s", device)

        # Load tokenizer
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                self.config.summary_model,
                token=self.config.hf_token,
                trust_remote_code=True,
            )
            # Set pad token if not present
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            tokenizer.padding_side = "right"
        except Exception as exc:
            raise ValueError(
                f"Failed to load tokenizer for {self.config.summary_model}: {str(exc)}"
            ) from exc

        # Configure quantization if enabled
        quantization_config = None
        if self.config.use_quantization:
            try:
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
                LOGGER.info("Quantization enabled (4-bit)")
            except Exception as exc:
                LOGGER.warning(
                    "Failed to configure quantization, loading model without it: %s",
                    str(exc),
                )
                quantization_config = None

        # Load model
        try:
            model_kwargs: Dict[str, Any] = {
                "token": self.config.hf_token,
                "trust_remote_code": True,
                "device_map": "auto" if device == "cuda" else None,
            }

            if quantization_config:
                model_kwargs["quantization_config"] = quantization_config
            elif device == "cpu":
                model_kwargs["torch_dtype"] = torch.float32
            else:
                model_kwargs["torch_dtype"] = torch.float16

            model = AutoModelForCausalLM.from_pretrained(
                self.config.summary_model, **model_kwargs
            )

            if device == "cpu" and not quantization_config:
                model = model.to(device)

            model.eval()  # Set to evaluation mode
            LOGGER.info("Model loaded successfully")

        except Exception as exc:
            raise ValueError(
                f"Failed to load model {self.config.summary_model}: {str(exc)}"
            ) from exc

        self._model = model
        self._tokenizer = tokenizer
        return model, tokenizer

    def generate_summaries(self, transcript: str) -> SummaryBundle:
        """Call the LLM to obtain short and comprehensive summaries.

        Args:
            transcript: Full transcript text to summarize.

        Returns:
            Dictionary with ``short_summary`` and ``comprehensive_summary`` keys.

        Raises:
            ValueError: If the transcript is empty or the model returns invalid data.

        """
        normalized = transcript.strip()
        if not normalized:
            raise ValueError("Transcript is empty; nothing to summarize.")

        # Load model on first use
        model, tokenizer = self._load_model()

        prompt = self._build_prompt(normalized)
        response = self._call_model(model, tokenizer, prompt)
        return self._parse_response(response)

    def _build_prompt(self, transcript: str) -> str:
        """Construct the prompt in Llama 3.1 instruction format.

        Args:
            transcript: Full transcript text to summarize.

        Returns:
            Formatted prompt string for Llama 3.1 model.
        """
        system_message = (
            "You are a senior financial analyst who writes clear summaries for busy "
            "executives. Produce a JSON object with keys 'short_summary' (<=80 words) "
            "and 'comprehensive_summary' (3-5 paragraphs with actionable insights). "
            "Keep factual accuracy high, avoid speculation, and mention key numbers "
            "when present. Return only valid JSON without any markdown formatting."
        )

        user_message = f"Transcript:\n{transcript}"

        # Llama 3.1 instruction format
        prompt = (
            "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            f"{system_message}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n"
            f"{user_message}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        )

        return prompt

    def _call_model(
        self, model: AutoModelForCausalLM, tokenizer: AutoTokenizer, prompt: str
    ) -> str:
        """Invoke the Hugging Face model to generate a summary.

        Args:
            model: Loaded Hugging Face model.
            tokenizer: Loaded tokenizer.
            prompt: Formatted prompt string.

        Returns:
            The raw response content from the model.

        Raises:
            ValueError: If the response format is unexpected or empty.
        """
        try:
            # Tokenize input
            inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096)

            # Move inputs to the same device as model
            device = next(model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}

            # Generate response
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=512,
                    temperature=0.2,
                    do_sample=True,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                    top_p=0.95,
                )

            # Decode response (skip the input tokens)
            input_length = inputs["input_ids"].shape[1]
            generated_tokens = outputs[0][input_length:]
            response_text = tokenizer.decode(generated_tokens, skip_special_tokens=True)

            if not response_text or not response_text.strip():
                raise ValueError("Model returned an empty response.")

            return response_text.strip()

        except Exception as exc:
            LOGGER.error("Error during model generation: %s", str(exc))
            raise ValueError(f"Model generation failed: {str(exc)}") from exc

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON from markdown code blocks if present.

        Args:
            text: Text that may contain JSON wrapped in markdown code blocks.

        Returns:
            The extracted JSON string, or the original text if no code blocks found.
        """
        # Pattern to match JSON in markdown code blocks (```json ... ``` or ``` ... ```)
        pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _parse_response(self, response_text: str) -> SummaryBundle:
        """Parse the LLM JSON payload and normalize whitespace.

        Args:
            response_text: Raw response text from the model.

        Returns:
            A SummaryBundle with parsed summaries.

        Raises:
            ValueError: If the response cannot be parsed or is missing required fields.
        """
        if not response_text or not response_text.strip():
            LOGGER.error("Received empty response from model")
            raise ValueError("Model response was empty.")

        # Try to extract JSON from markdown code blocks if present
        cleaned_text = self._extract_json_from_markdown(response_text)

        # Sometimes the model may include extra text before/after JSON
        # Try to find JSON object in the text
        json_match = re.search(r"\{.*\}", cleaned_text, re.DOTALL)
        if json_match:
            cleaned_text = json_match.group(0)

        try:
            parsed: Dict[str, str] = json.loads(cleaned_text)
        except json.JSONDecodeError as exc:
            LOGGER.error(
                "Failed to parse JSON response. Response text (first 500 chars): %s",
                response_text[:500],
            )
            raise ValueError(
                f"Model response was not valid JSON: {str(exc)}"
            ) from exc

        try:
            short_raw = parsed["short_summary"]
            comprehensive_raw = parsed["comprehensive_summary"]
        except KeyError as exc:
            LOGGER.error(
                "Response missing required keys. Available keys: %s",
                list(parsed.keys()),
            )
            raise ValueError(
                f"Model response missing summary keys: {str(exc)}"
            ) from exc

        # Convert to string if the value is not already a string (e.g., dict, list)
        if isinstance(short_raw, dict):
            LOGGER.warning(
                "short_summary is a dict, converting to JSON string. Value: %s",
                short_raw,
            )
            short = json.dumps(short_raw, indent=2)
        elif isinstance(short_raw, list):
            short = " ".join(str(item) for item in short_raw)
        else:
            short = str(short_raw).strip()

        if isinstance(comprehensive_raw, dict):
            LOGGER.warning(
                "comprehensive_summary is a dict, converting to JSON string. Value: %s",
                comprehensive_raw,
            )
            comprehensive = json.dumps(comprehensive_raw, indent=2)
        elif isinstance(comprehensive_raw, list):
            comprehensive = " ".join(str(item) for item in comprehensive_raw)
        else:
            comprehensive = str(comprehensive_raw).strip()

        if not short or not comprehensive:
            raise ValueError("Summaries must not be empty.")
        return SummaryBundle(
            short_summary=short,
            comprehensive_summary=comprehensive,
        )
