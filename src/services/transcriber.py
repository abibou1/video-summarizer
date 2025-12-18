# src/services/transcriber.py
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI, Timeout as OpenAITimeout
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    TranscriptList,
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

        Args:
            config: Application configuration object.

        Raises:
            ValueError: If OpenAI API key is not provided (required for Whisper fallback).

        """
        self.config = config
        if not config.openai_api_key:
            raise ValueError(
                "OpenAI API key is required for Whisper transcription. "
                "Set OPENAI_API_KEY environment variable."
            )
        # Ensure downloads directory exists (important for Lambda /tmp directory)
        config.downloads_dir.mkdir(parents=True, exist_ok=True)
        # Configure OpenAI client with timeout (30 minutes for long videos)
        self.client = OpenAI(
            api_key=config.openai_api_key,
            timeout=OpenAITimeout(1800.0, connect=60.0, read=1800.0, write=60.0),
        )
        # Timeout settings (in seconds)
        self.download_timeout = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "600"))  # 10 minutes
        self.transcription_timeout = int(os.getenv("TRANSCRIPTION_TIMEOUT_SECONDS", "1800"))  # 30 minutes

    def get_youtube_transcript(self, video_id: str) -> Optional[str]:
        """Fetch transcript directly from YouTube if available.

        Implements strict transcript-first approach with priority:
        1. Manually created transcripts (prefer English, fallback to first available)
        2. Auto-generated transcripts (prefer English, fallback to first available)
        3. Returns None if no transcripts available (triggers audio download fallback)

        Args:
            video_id: Identifier of the YouTube video.

        Returns:
            Combined transcript text if available, None otherwise.

        """
        try:
            LOGGER.info("Attempting to fetch YouTube transcript for video %s", video_id)
            
            # List all available transcripts
            transcript_list: TranscriptList = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Step 1: Try manually created transcripts first
            manual_transcripts = [
                transcript for transcript in transcript_list
                if not transcript.is_generated
            ]
            
            if manual_transcripts:
                LOGGER.info(
                    "Found %d manually created transcript(s) for video %s",
                    len(manual_transcripts),
                    video_id,
                )
                
                # Prefer English manual transcript
                english_manual = next(
                    (t for t in manual_transcripts if t.language_code == "en"),
                    None,
                )
                
                if english_manual:
                    LOGGER.info(
                        "Using English manually created transcript for video %s",
                        video_id,
                    )
                    transcript_data = english_manual.fetch()
                    transcript_text = " ".join([entry["text"] for entry in transcript_data])
                    LOGGER.info(
                        "Successfully retrieved English manual transcript for video %s (%d entries, %d characters)",
                        video_id,
                        len(transcript_data),
                        len(transcript_text),
                    )
                    return transcript_text
                
                # Fallback to first available manual transcript
                first_manual = manual_transcripts[0]
                LOGGER.info(
                    "Using first available manually created transcript (language: %s) for video %s",
                    first_manual.language_code,
                    video_id,
                )
                transcript_data = first_manual.fetch()
                transcript_text = " ".join([entry["text"] for entry in transcript_data])
                LOGGER.info(
                    "Successfully retrieved manual transcript (language: %s) for video %s (%d entries, %d characters)",
                    first_manual.language_code,
                    video_id,
                    len(transcript_data),
                    len(transcript_text),
                )
                return transcript_text
            
            # Step 2: Try auto-generated transcripts if no manual transcripts found
            auto_transcripts = [
                transcript for transcript in transcript_list
                if transcript.is_generated
            ]
            
            if auto_transcripts:
                LOGGER.info(
                    "Found %d auto-generated transcript(s) for video %s (no manual transcripts available)",
                    len(auto_transcripts),
                    video_id,
                )
                
                # Prefer English auto-generated transcript
                english_auto = next(
                    (t for t in auto_transcripts if t.language_code == "en"),
                    None,
                )
                
                if english_auto:
                    LOGGER.info(
                        "Using English auto-generated transcript for video %s",
                        video_id,
                    )
                    transcript_data = english_auto.fetch()
                    transcript_text = " ".join([entry["text"] for entry in transcript_data])
                    LOGGER.info(
                        "Successfully retrieved English auto-generated transcript for video %s (%d entries, %d characters)",
                        video_id,
                        len(transcript_data),
                        len(transcript_text),
                    )
                    return transcript_text
                
                # Fallback to first available auto-generated transcript
                first_auto = auto_transcripts[0]
                LOGGER.info(
                    "Using first available auto-generated transcript (language: %s) for video %s",
                    first_auto.language_code,
                    video_id,
                )
                transcript_data = first_auto.fetch()
                transcript_text = " ".join([entry["text"] for entry in transcript_data])
                LOGGER.info(
                    "Successfully retrieved auto-generated transcript (language: %s) for video %s (%d entries, %d characters)",
                    first_auto.language_code,
                    video_id,
                    len(transcript_data),
                    len(transcript_text),
                )
                return transcript_text
            
            # No transcripts available
            LOGGER.warning(
                "No transcripts (manual or auto-generated) found for video %s, falling back to Whisper",
                video_id,
            )
            return None
            
        except NoTranscriptFound:
            LOGGER.warning(
                "No transcript found for video %s, falling back to Whisper",
                video_id,
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
                "Error fetching YouTube transcript for video %s: %s (%s). Falling back to Whisper",
                video_id,
                exc,
                type(exc).__name__,
            )
            return None

    def download_audio(self, video_id: str) -> Path:
        """Download the YouTube video's audio track as an intermediate file.

        This method is only called as a last-resort fallback when transcript
        retrieval completely fails. yt-dlp is imported lazily here to ensure
        it's never loaded if a transcript exists.

        Args:
            video_id: Identifier of the YouTube video.

        Returns:
            Path pointing to the downloaded media file.

        Raises:
            RuntimeError: If yt-dlp is unable to download the video within timeout.

        """
        # Lazy import: yt-dlp is only imported when transcript retrieval fails
        # This enforces the strict transcript-first invariant
        from yt_dlp import YoutubeDL  # noqa: PLC0415
        
        url = f"https://www.youtube.com/watch?v={video_id}"
        output_template = str(self.config.downloads_dir / f"{video_id}.%(ext)s")
        download_start_time = time.time()

        # Progress hook for logging download progress
        def progress_hook(d: dict) -> None:
            if d["status"] == "downloading":
                downloaded_bytes = d.get("downloaded_bytes", 0)
                total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                if total_bytes > 0:
                    percent = (downloaded_bytes / total_bytes) * 100
                    LOGGER.info(
                        "Download progress: %.1f%% (%d/%d bytes) for video %s",
                        percent,
                        downloaded_bytes,
                        total_bytes,
                        video_id,
                    )
                else:
                    LOGGER.debug(
                        "Downloading: %d bytes downloaded for video %s",
                        downloaded_bytes,
                        video_id,
                    )
            elif d["status"] == "finished":
                elapsed = time.time() - download_start_time
                LOGGER.info(
                    "Download completed in %.1f seconds for video %s",
                    elapsed,
                    video_id,
                )

        ydl_opts = {
            "format": "140/bestaudio/best",  # prefer m4a
            "quiet": False,  # Enable logging
            "no_warnings": False,  # Show warnings
            "cachedir": False,
            "outtmpl": output_template,
            "socket_timeout": 30,  # 30 second socket timeout
            "progress_hooks": [progress_hook],
        }

        LOGGER.info("Starting audio download for video %s (timeout: %d seconds)", video_id, self.download_timeout)
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                downloaded = Path(ydl.prepare_filename(info))
                elapsed = time.time() - download_start_time
                file_size = downloaded.stat().st_size if downloaded.exists() else 0
                LOGGER.info(
                    "Audio download completed: %s (%.1f MB, took %.1f seconds)",
                    downloaded.name,
                    file_size / (1024 * 1024),
                    elapsed,
                )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.time() - download_start_time
            LOGGER.error(
                "Failed to download audio for %s after %.1f seconds: %s",
                video_id,
                elapsed,
                exc,
            )
            raise RuntimeError(
                f"Failed to download audio for {video_id} after {elapsed:.1f} seconds: {exc}"
            ) from exc
        return downloaded

    def transcribe(self, video_id: str) -> str:
        """Transcribe a YouTube video, using YouTube transcripts when available.

        Attempts to fetch YouTube transcripts first. If unavailable, falls back
        to Whisper transcription via OpenAI API.

        Args:
            video_id: Identifier of the YouTube video.

        Returns:
            Transcript text for the provided video.

        Raises:
            RuntimeError: If transcription fails or times out.

        Example:
            >>> transcriber = WhisperTranscriber(config)
            >>> text = transcriber.transcribe("dQw4w9WgXcQ")

        """
        # Try YouTube transcript first (no download required)
        LOGGER.info("Attempting to transcribe video %s", video_id)
        youtube_transcript = self.get_youtube_transcript(video_id)
        if youtube_transcript is not None:
            LOGGER.info("Using YouTube transcript for video %s", video_id)
            return youtube_transcript

        # Fall back to Whisper transcription
        LOGGER.info("Using Whisper transcription for video %s", video_id)
        transcription_start_time = time.time()
        audio_path = self.download_audio(video_id)
        
        try:
            file_size = audio_path.stat().st_size if audio_path.exists() else 0
            LOGGER.info(
                "Starting Whisper transcription for video %s (file size: %.1f MB, timeout: %d seconds)",
                video_id,
                file_size / (1024 * 1024),
                self.transcription_timeout,
            )
            
            with audio_path.open("rb") as audio_file:
                LOGGER.info("Sending audio file to Whisper API...")
                transcript_text = self.client.audio.transcriptions.create(
                    model=self.config.whisper_model,
                    file=audio_file,
                    response_format="text",
                )
                
            elapsed = time.time() - transcription_start_time
            LOGGER.info(
                "Whisper transcription completed for video %s in %.1f seconds",
                video_id,
                elapsed,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.time() - transcription_start_time
            LOGGER.error(
                "Whisper transcription failed for video %s after %.1f seconds: %s",
                video_id,
                elapsed,
                exc,
            )
            raise RuntimeError(
                f"Whisper transcription failed for {video_id} after {elapsed:.1f} seconds: {exc}"
            ) from exc
        finally:
            try:
                if audio_path.exists():
                    os.remove(audio_path)
                    LOGGER.debug("Cleaned up temporary audio file: %s", audio_path)
            except OSError as exc:
                LOGGER.warning("Failed to remove temp audio file %s: %s", audio_path, exc)

        transcript_str = transcript_text if isinstance(transcript_text, str) else str(
            transcript_text
        )
        
        LOGGER.info(
            "Transcription completed for video %s: %d characters generated",
            video_id,
            len(transcript_str),
        )

        return transcript_str

