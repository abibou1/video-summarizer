# src/services/summarizer.py
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, TypedDict

from huggingface_hub import InferenceClient

from config.config import Config

LOGGER = logging.getLogger(__name__)


class SummaryBundle(TypedDict):
    """Container for short and comprehensive summaries."""

    short_summary: str
    comprehensive_summary: str


@dataclass
class TranscriptSummarizer:
    """Generate multi-length summaries for saved transcripts using Hugging Face Inference API."""

    config: Config
    _client: Optional[InferenceClient] = None

    def __post_init__(self) -> None:
        """Initialize Inference API client lazily on first use."""
        # Client will be initialized on first call to generate_summaries
        pass

    def _get_client(self) -> InferenceClient:
        """Get or create the Hugging Face Inference API client.

        Returns:
            InferenceClient instance configured with the HF token.

        """
        if self._client is not None:
            return self._client

        if not self.config.hf_token:
            raise ValueError(
                "HF_TOKEN is required for Hugging Face Inference API. "
                "Set HF_TOKEN environment variable in your .env file."
            )

        self._client = InferenceClient(
            model=self.config.summary_model,
            token=self.config.hf_token,
        )
        LOGGER.info("Initialized Hugging Face Inference API client for model: %s", self.config.summary_model)
        return self._client

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

        client = self._get_client()
        prompt = self._build_prompt(normalized)
        response = self._call_model(client, prompt)
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

    def _call_model(self, client: InferenceClient, prompt: str) -> str:
        """Invoke the Hugging Face Inference API to generate a summary.

        Args:
            client: Hugging Face Inference API client.
            prompt: Formatted prompt string.

        Returns:
            The raw response content from the model.

        Raises:
            ValueError: If the response format is unexpected or empty.
        """
        try:
            LOGGER.info("Calling Hugging Face Inference API...")
            response = client.text_generation(
                prompt=prompt,
                max_new_tokens=512,
                temperature=0.2,
                return_full_text=False,
            )

            if not response or not response.strip():
                raise ValueError("Model returned an empty response.")

            return response.strip()

        except Exception as exc:
            error_str = str(exc)
            LOGGER.error("Error during model generation: %s", error_str)

            # Provide helpful error messages for common issues
            if "401" in error_str or "Unauthorized" in error_str:
                raise ValueError(
                    "Authentication failed. Please check your HF_TOKEN in the .env file. "
                    "Get your token from https://huggingface.co/settings/tokens"
                ) from exc
            elif "403" in error_str or "gated" in error_str.lower():
                raise ValueError(
                    f"Access denied to model '{self.config.summary_model}'. "
                    f"Visit https://huggingface.co/{self.config.summary_model} to request access. "
                    "Make sure your HF_TOKEN is set correctly."
                ) from exc
            elif "404" in error_str:
                raise ValueError(
                    f"Model '{self.config.summary_model}' not found. "
                    "Please check the model name in your SUMMARY_MODEL configuration."
                ) from exc

            raise ValueError(f"Model generation failed: {error_str}") from exc

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
