from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from openai import OpenAI
from pytube import YouTube

from config import Config

LOGGER = logging.getLogger(__name__)


class WhisperTranscriber:
    def __init__(self, config: Config):
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def download_audio(self, video_id: str) -> Path:
        url = f"https://www.youtube.com/watch?v={video_id}"
        yt = YouTube(url)
        stream = yt.streams.filter(only_audio=True).first()
        if stream is None:
            raise RuntimeError(f"No audio stream available for {video_id}")
        output_path = stream.download(
            output_path=str(self.config.downloads_dir),
            filename=f"{video_id}.mp4",
        )
        return Path(output_path)

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

