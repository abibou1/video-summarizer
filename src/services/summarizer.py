# src/services/summarizer.py
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, TypedDict

from openai import OpenAI

from src.core.config import Config

LOGGER = logging.getLogger(__name__)


class SummaryBundle(TypedDict):
    """Container for short and comprehensive summaries."""

    short_summary: str
    comprehensive_summary: str


@dataclass
class TranscriptSummarizer:
    """Generate multi-length summaries for saved transcripts."""

    config: Config
    client: Optional[OpenAI] = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = OpenAI(api_key=self.config.openai_api_key)

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

        prompt = self._build_prompt(normalized)
        response = self._call_model(prompt)
        return self._parse_response(response)

    def _build_prompt(self, transcript: str) -> str:
        """Construct the user prompt instructing the LLM how to summarize."""

        return (
            "You are a senior financial analyst who writes clear summaries for busy "
            "executives. Produce a JSON object with keys 'short_summary' (<=80 words) "
            "and 'comprehensive_summary' (3-5 paragraphs with actionable insights). "
            "Keep factual accuracy high, avoid speculation, and mention key numbers "
            "when present. Return only valid JSON without any markdown formatting.\n\n"
            "Transcript:\n"
            f"{transcript}"
        )

    def _call_model(self, prompt: str) -> str:
        """Invoke the OpenAI Chat Completions API.

        Returns:
            The raw response content from the model.

        Raises:
            ValueError: If the response format is unexpected or empty.
        """
        assert self.client is not None  # Defensive for type-checkers
        completion = self.client.chat.completions.create(
            model=self.config.summary_model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You convert transcripts into structured summaries. Always return valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        try:
            content = completion.choices[0].message.content
            if not content:
                raise ValueError("Model returned an empty response.")
            return content
        except (AttributeError, IndexError) as exc:  # pragma: no cover - defensive
            raise ValueError("Model returned an unexpected response format.") from exc

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
            short = parsed["short_summary"].strip()
            comprehensive = parsed["comprehensive_summary"].strip()
        except KeyError as exc:
            LOGGER.error(
                "Response missing required keys. Available keys: %s",
                list(parsed.keys()),
            )
            raise ValueError(
                f"Model response missing summary keys: {str(exc)}"
            ) from exc

        if not short or not comprehensive:
            raise ValueError("Summaries must not be empty.")
        return SummaryBundle(
            short_summary=short,
            comprehensive_summary=comprehensive,
        )

