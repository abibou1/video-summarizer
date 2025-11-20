from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from openai import OpenAI
from yt_dlp import YoutubeDL

from config import Config

LOGGER = logging.getLogger(__name__)


class WhisperTranscriber:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def download_audio(self, video_id: str) -> Path:
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_template = str(self.config.downloads_dir / f"{video_id}.%(ext)s")

        ydl_opts = {
            "format": "140/bestaudio/best",  # prefer m4a
            "quiet": True,
            "no_warnings": True,
            "cachedir": False,
            "outtmpl": output_template,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded = Path(ydl.prepare_filename(info))
        return downloaded

    def transcribe(
        self, video_id: str, title: Optional[str] = None, write_file: bool = True
    ) -> Tuple[str, Optional[Path]]:
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

        transcript_path = None
        if write_file:
            safe_title = (title or video_id).replace("/", "_")
            transcript_path = self.config.transcripts_dir / f"{safe_title}.txt"
            transcript_path.write_text(transcript_str, encoding="utf-8")

        return transcript_str, transcript_path

