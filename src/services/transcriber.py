# src/services/transcriber.py
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI
from yt_dlp import YoutubeDL
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from config.config import Config

LOGGER = logging.getLogger(__name__)


class WhisperTranscriber:
    """Wrapper around OpenAI Whisper that handles audio downloads and cleanup.

    Attempts to use YouTube transcripts first when available, falling back to
    Whisper transcription when transcripts are unavailable.
    """

    def __init__(self, config: Config):
        """Initialize the transcriber with application configuration.

        Raises:
            ValueError: If OpenAI API key is not provided (required for Whisper fallback).
        """
        self.config = config
        if not config.openai_api_key:
            raise ValueError(
                "OpenAI API key is required for Whisper transcription. "
                "Set OPENAI_API_KEY environment variable."
            )
        self.client = OpenAI(api_key=config.openai_api_key)

    def get_youtube_transcript(self, video_id: str) -> Optional[str]:
        """Fetch transcript directly from YouTube if available.

        Args:
            video_id: Identifier of the YouTube video.

        Returns:
            Combined transcript text if available, None otherwise.

        """
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(
                video_id, languages=["en"]
            )
            # Combine all transcript entries into a single text string
            transcript_text = " ".join([entry["text"] for entry in transcript_list])
            LOGGER.info(
                "Successfully retrieved YouTube transcript for video %s (%d entries)",
                video_id,
                len(transcript_list),
            )
            return transcript_text
        except NoTranscriptFound:
            LOGGER.warning(
                "No transcript found for video %s, falling back to Whisper", video_id
            )
            return None
        except TranscriptsDisabled:
            LOGGER.warning(
                "Transcripts disabled for video %s, falling back to Whisper", video_id
            )
            return None
        except VideoUnavailable:
            LOGGER.warning(
                "Video %s is unavailable, falling back to Whisper", video_id
            )
            return None
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Error fetching YouTube transcript for video %s: %s. Falling back to Whisper",
                video_id,
                exc,
            )
            return None

    def download_audio(self, video_id: str) -> Path:
        """Download the YouTube video's audio track as an intermediate file.

        Args:
            video_id: Identifier of the YouTube video.

        Returns:
            Path pointing to the downloaded media file.

        Raises:
            RuntimeError: If youtube-dl is unable to download the video.

        """
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_template = str(self.config.downloads_dir / f"{video_id}.%(ext)s")

        ydl_opts = {
            "format": "140/bestaudio/best",  # prefer m4a
            "quiet": True,
            "no_warnings": True,
            "cachedir": False,
            "outtmpl": output_template,
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded = Path(ydl.prepare_filename(info))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to download audio for {video_id}") from exc
        return downloaded

    def transcribe(self, video_id: str) -> str:
        """Transcribe a YouTube video, using YouTube transcripts when available.

        Attempts to fetch YouTube transcripts first. If unavailable, falls back
        to Whisper transcription via OpenAI API.

        Args:
            video_id: Identifier of the YouTube video.

        Returns:
            Transcript text for the provided video.

        Example:
            >>> transcriber = WhisperTranscriber(config)
            >>> text = transcriber.transcribe("dQw4w9WgXcQ")

        """
        # Try YouTube transcript first (no download required)
        youtube_transcript = self.get_youtube_transcript(video_id)
        if youtube_transcript is not None:
            LOGGER.info("Using YouTube transcript for video %s", video_id)
            return youtube_transcript

        # Fall back to Whisper transcription
        LOGGER.info("Using Whisper transcription for video %s", video_id)
        audio_path = self.download_audio(video_id)
        try:
            with audio_path.open("rb") as audio_file:
                transcript_text = self.client.audio.transcriptions.create(
                    model=self.config.whisper_model,
                    file=audio_file,
                    response_format="text",
                )
        finally:
            try:
                os.remove(audio_path)
            except OSError:
                LOGGER.warning("Failed to remove temp audio file %s", audio_path)

        transcript_str = transcript_text if isinstance(transcript_text, str) else str(
            transcript_text
        )

        return transcript_str

