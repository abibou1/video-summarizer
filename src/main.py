# src/main.py
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Add project root to Python path to allow imports of config and src modules
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config.config import Config, load_config, load_last_video_id, save_last_video_id
from src.services.email_service import EmailService
from src.services.summarizer import TranscriptSummarizer
from src.services.transcriber import WhisperTranscriber
from src.services.youtube_poller import YouTubePoller

# Import AWS services only when needed to avoid import errors in non-AWS environments
try:
    from src.core.aws_services import S3StateManager
except ImportError:
    S3StateManager = None  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


def process_latest_video(
    poller: YouTubePoller,
    transcriber: WhisperTranscriber,
    config: Config,
    summarizer: TranscriptSummarizer | None = None,
    email_service: EmailService | None = None,
    notify_no_new_videos: bool = False,
) -> None:
    """Download and transcribe the latest upload if it is new.

    Args:
        poller: Component responsible for discovering YouTube uploads.
        transcriber: Component responsible for downloading audio and invoking Whisper.
        config: Configuration object containing state management settings.
        summarizer: Optional component that generates summaries for the transcript.
        email_service: Optional component responsible for emailing summaries.
        notify_no_new_videos: If True, send email notification when no new videos are detected.

    """
    last_video_id = load_last_video_id(config)
    latest = poller.fetch_latest_video()
    if not latest:
        LOGGER.info("No videos found.")
        return
    if latest["video_id"] == last_video_id:
        LOGGER.info("No new videos since last check.")
        if notify_no_new_videos and email_service:
            try:
                # Load last video title from state (S3 or local filesystem)
                last_video_title: str | None = None
                try:
                    if config.use_aws and config.s3_state_bucket and S3StateManager is not None:
                        s3_manager = S3StateManager(
                            bucket_name=config.s3_state_bucket, region=config.aws_region
                        )
                        state_data = s3_manager.load_state()
                        last_video_title = state_data.get("last_video_title") or None
                    elif config.state_file.exists():
                        state_data = json.loads(config.state_file.read_text(encoding="utf-8"))
                        last_video_title = state_data.get("last_video_title") or None
                except Exception:  # noqa: BLE001
                    # If loading state fails, continue without title
                    pass
                LOGGER.info(
                    "Attempting to send no new videos notification email to %s via SMTP (host inferred from %s)",
                    email_service.config.smtp_recipient,
                    email_service.config.smtp_sender,
                )
                email_service.send_no_new_videos_email(last_video_title)
                LOGGER.info("No new videos notification email sent successfully")
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Failed to send no new videos notification email: %s", exc)
        return

    LOGGER.info("New video detected: %s", latest["title"])
    transcript = transcriber.transcribe(latest["video_id"])
    save_last_video_id(
        config,
        latest["video_id"],
        title=latest["title"],
    )
    LOGGER.debug("Transcript content:\n%s", transcript)

    summaries = None
    error_reason: str = "Unknown error: Unable to generate summaries."

    # Check if transcript is valid first
    if not transcript or not transcript.strip():
        error_reason = "Transcript is empty or invalid, unable to generate summaries."
        LOGGER.warning(error_reason)
    elif summarizer:
        try:
            summaries = summarizer.generate_summaries(transcript)
            LOGGER.info("Generated summaries for %s", latest["title"])
            # Print summaries to console
            print("\n" + "=" * 80)
            print(f"SUMMARIES FOR: {latest['title']}")
            print("=" * 80)
            print(f"\nSHORT SUMMARY:\n{summaries['short_summary']}\n")
            print(f"\nCOMPREHENSIVE SUMMARY:\n{summaries['comprehensive_summary']}\n")
            print("=" * 80 + "\n")
        except Exception as exc:  # noqa: BLE001
            error_reason = f"Failed to generate summaries: {str(exc)}"
            LOGGER.exception("Failed to summarize transcript: %s", exc)
    else:
        error_reason = (
            "Summarizer was not initialized. Email summaries may be disabled in configuration."
        )
        LOGGER.warning("Summarizer not initialized. Email enabled: %s", email_service is not None)

    if email_service:
        try:
            if summaries:
                LOGGER.info(
                    "Attempting to send summary email to %s via SMTP (host inferred from %s)",
                    email_service.config.smtp_recipient,
                    email_service.config.smtp_sender,
                )
                email_service.send_summary_email(latest["title"], summaries)
                LOGGER.info("Summary email sent successfully")
            else:
                LOGGER.info(
                    "Attempting to send error notification email to %s via SMTP (host inferred from %s)",
                    email_service.config.smtp_recipient,
                    email_service.config.smtp_sender,
                )
                email_service.send_error_email(latest["title"], error_reason)
                LOGGER.info("Error notification email sent successfully")
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to send email: %s", exc)
    else:
        LOGGER.debug("Email service not initialized (email_enabled may be False)")


def run_once() -> None:
    """Execute a single poll-transcribe cycle."""
    config = load_config()
    LOGGER.info("Email enabled: %s", config.email_enabled)
    if config.email_enabled:
        LOGGER.info(
            "Email configuration - Sender: %s, Recipient: %s, Port: %d",
            config.smtp_sender,
            config.smtp_recipient,
            config.smtp_port,
        )
    poller = YouTubePoller(config)
    transcriber = WhisperTranscriber(config)
    summarizer = TranscriptSummarizer(config) if config.email_enabled else None
    email_service = EmailService(config) if config.email_enabled else None
    process_latest_video(
        poller,
        transcriber,
        config,
        summarizer=summarizer,
        email_service=email_service,
        notify_no_new_videos=True,
    )


def run_loop(config: Config) -> None:
    """Continuously run the poll-transcribe cycle.

    Args:
        config: Application configuration loaded from the environment.

    """
    LOGGER.info("Email enabled: %s", config.email_enabled)
    if config.email_enabled:
        LOGGER.info(
            "Email configuration - Sender: %s, Recipient: %s, Port: %d",
            config.smtp_sender,
            config.smtp_recipient,
            config.smtp_port,
        )
    poller = YouTubePoller(config)
    transcriber = WhisperTranscriber(config)
    summarizer = TranscriptSummarizer(config) if config.email_enabled else None
    email_service = EmailService(config) if config.email_enabled else None
    while True:
        process_latest_video(
            poller,
            transcriber,
            config,
            summarizer=summarizer,
            email_service=email_service,
        )
        LOGGER.info("Sleeping for %s seconds", config.poll_interval_seconds)
        time.sleep(config.poll_interval_seconds)


def process_dummy_transcript(
    transcript_path: Path,
    summarizer: TranscriptSummarizer | None = None,
    email_service: EmailService | None = None,
) -> None:
    """Process a dummy transcript file for development purposes.

    This function reads a transcript from a file, generates summaries, and sends emails
    without requiring YouTube polling or video transcription. Useful for testing the
    summarization and email pipeline during development.

    Args:
        transcript_path: Path to the dummy transcript file.
        summarizer: Optional component that generates summaries for the transcript.
        email_service: Optional component responsible for emailing summaries.

    Raises:
        FileNotFoundError: If the transcript file does not exist.
        IOError: If the transcript file cannot be read.

    """
    LOGGER.info("Running in development mode with dummy transcript")
    if not transcript_path.exists():
        raise FileNotFoundError(f"Dummy transcript file not found: {transcript_path}")

    LOGGER.info("Reading dummy transcript from %s", transcript_path)
    try:
        transcript = transcript_path.read_text(encoding="utf-8")
    except IOError as exc:
        raise IOError(f"Failed to read transcript file: {transcript_path}") from exc

    dummy_title = "Dummy Video - Development Mode"
    LOGGER.debug("Transcript content:\n%s", transcript)

    summaries = None
    error_reason: str = "Unknown error: Unable to generate summaries."

    if not transcript.strip():
        error_reason = "Transcript is empty or invalid, unable to generate summaries."
        LOGGER.warning("Dummy transcript file is empty")
    elif summarizer:
        try:
            summaries = summarizer.generate_summaries(transcript)
            LOGGER.info("Generated summaries for %s", dummy_title)
            # Print summaries to console
            print("\n" + "=" * 80)
            print(f"SUMMARIES FOR: {dummy_title}")
            print("=" * 80)
            print(f"\nSHORT SUMMARY:\n{summaries['short_summary']}\n")
            print(f"\nCOMPREHENSIVE SUMMARY:\n{summaries['comprehensive_summary']}\n")
            print("=" * 80 + "\n")
        except Exception as exc:  # noqa: BLE001
            error_reason = f"Failed to generate summaries: {str(exc)}"
            LOGGER.exception("Failed to summarize transcript: %s", exc)
    else:
        error_reason = (
            "Summarizer was not initialized. Email summaries may be disabled in configuration."
        )
        LOGGER.warning("Summarizer not initialized. Email enabled: %s", email_service is not None)

    if email_service:
        try:
            if summaries:
                LOGGER.info(
                    "Attempting to send summary email to %s via SMTP (host inferred from %s)",
                    email_service.config.smtp_recipient,
                    email_service.config.smtp_sender,
                )
                email_service.send_summary_email(dummy_title, summaries)
                LOGGER.info("Summary email sent successfully")
            else:
                LOGGER.info(
                    "Attempting to send error notification email to %s via SMTP (host inferred from %s)",
                    email_service.config.smtp_recipient,
                    email_service.config.smtp_sender,
                )
                email_service.send_error_email(dummy_title, error_reason)
                LOGGER.info("Error notification email sent successfully")
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to send email: %s", exc)
    else:
        LOGGER.debug("Email service not initialized (email_enabled may be False)")


def run_dev() -> None:
    """Execute development mode using dummy transcript file.

    This mode skips YouTube polling and video transcription, instead reading
    a transcript from data/transcript.txt. It still generates summaries and
    sends emails if configured.

    """
    config = load_config()
    LOGGER.info("Email enabled: %s", config.email_enabled)
    if config.email_enabled:
        LOGGER.info(
            "Email configuration - Sender: %s, Recipient: %s, Port: %d",
            config.smtp_sender,
            config.smtp_recipient,
            config.smtp_port,
        )
    summarizer = TranscriptSummarizer(config) if config.email_enabled else None
    email_service = EmailService(config) if config.email_enabled else None

    # Use data/transcript.txt as the dummy transcript file
    transcript_path = Path("data/transcript.txt")
    process_dummy_transcript(
        transcript_path,
        summarizer=summarizer,
        email_service=email_service,
    )


def main() -> None:
    """CLI entry point for the YouTube transcription automation."""
    parser = argparse.ArgumentParser(description="Poll YouTube channel for new videos")
    parser.add_argument(
        "--mode",
        choices=["once", "loop", "dev"],
        default="once",
        help="Run once, continuously, or in development mode with dummy transcript",
    )
    args = parser.parse_args()

    if args.mode == "loop":
        config = load_config()
        run_loop(config)
    elif args.mode == "dev":
        run_dev()
    else:
        run_once()


if __name__ == "__main__":
    main()

