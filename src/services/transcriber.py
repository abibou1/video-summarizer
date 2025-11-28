# src/services/transcriber.py
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI
from yt_dlp import YoutubeDL

from config.config import Config

LOGGER = logging.getLogger(__name__)


class WhisperTranscriber:
    """Wrapper around OpenAI Whisper that handles audio downloads and cleanup."""

    def __init__(self, config: Config):
        """Initialize the transcriber with application configuration."""

        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

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
        """Transcribe a YouTube video via Whisper.

        Args:
            video_id: Identifier of the YouTube video.

        Returns:
            Transcript text for the provided video.

        Example:
            >>> transcriber = WhisperTranscriber(config)
            >>> text = transcriber.transcribe("dQw4w9WgXcQ")

        """
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

