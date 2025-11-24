from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, TypedDict

from openai import OpenAI

from config import Config, load_last_video_metadata

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

    def load_latest_transcript_text(self) -> str:
        """Load transcript text recorded in the persisted processing state."""

        metadata = load_last_video_metadata(self.config.state_file)
        transcript_path = metadata.get("last_transcript_path")
        if not transcript_path:
            raise FileNotFoundError(
                "No transcript path stored in state; cannot summarize."
            )
        path = Path(transcript_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Transcript file {transcript_path} referenced in state was not found."
            )
        return path.read_text(encoding="utf-8")

    def summarize_latest_transcript(self) -> SummaryBundle:
        """Load the latest transcript and return structured summaries."""

        transcript = self.load_latest_transcript_text()
        return self.generate_summaries(transcript)

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
            "executives. Produce JSON with keys short_summary (<=80 words) and "
            "comprehensive_summary (3-5 paragraphs with actionable insights). "
            "Keep factual accuracy high, avoid speculation, and mention key numbers "
            "when present.\n\nTranscript:\n"
            f"{transcript}"
        )

    def _call_model(self, prompt: str) -> str:
        """Invoke the OpenAI Chat Completions API."""

        assert self.client is not None  # Defensive for type-checkers
        completion = self.client.chat.completions.create(
            model=self.config.summary_model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": "You convert transcripts into structured summaries.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        try:
            return completion.choices[0].message.content or ""
        except (AttributeError, IndexError) as exc:  # pragma: no cover - defensive
            raise ValueError("Model returned an unexpected response format.") from exc

    def _parse_response(self, response_text: str) -> SummaryBundle:
        """Parse the LLM JSON payload and normalize whitespace."""

        try:
            parsed: Dict[str, str] = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise ValueError("Model response was not valid JSON.") from exc

        try:
            short = parsed["short_summary"].strip()
            comprehensive = parsed["comprehensive_summary"].strip()
        except KeyError as exc:
            raise ValueError("Model response missing summary keys.") from exc

        if not short or not comprehensive:
            raise ValueError("Summaries must not be empty.")
        return SummaryBundle(
            short_summary=short,
            comprehensive_summary=comprehensive,
        )

