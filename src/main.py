# src/main.py
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from src.core.config import Config, load_config, load_last_video_id, save_last_video_id
from src.services.email_service import EmailService
from src.services.summarizer import TranscriptSummarizer
from src.services.transcriber import WhisperTranscriber
from src.services.youtube_poller import YouTubePoller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


def process_latest_video(
    poller: YouTubePoller,
    transcriber: WhisperTranscriber,
    state_file: Path,
    summarizer: TranscriptSummarizer | None = None,
    email_service: EmailService | None = None,
) -> None:
    """Download and transcribe the latest upload if it is new.

    Args:
        poller: Component responsible for discovering YouTube uploads.
        transcriber: Component responsible for downloading audio and invoking Whisper.
        state_file: Path to the persisted JSON file storing the last processed video ID.
        summarizer: Optional component that generates summaries for the transcript.
        email_service: Optional component responsible for emailing summaries.

    """
    last_video_id = load_last_video_id(state_file)
    latest = poller.fetch_latest_video()
    if not latest:
        LOGGER.info("No videos found.")
        return
    if latest["video_id"] == last_video_id:
        LOGGER.info("No new videos since last check.")
        return

    LOGGER.info("New video detected: %s", latest["title"])
    transcript = transcriber.transcribe(latest["video_id"])
    save_last_video_id(
        state_file,
        latest["video_id"],
        title=latest["title"],
    )
    LOGGER.debug("Transcript content:\n%s", transcript)

    summaries = None
    if summarizer:
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
            LOGGER.exception("Failed to summarize transcript: %s", exc)
    else:
        LOGGER.warning("Summarizer not initialized. Email enabled: %s", email_service is not None)

    if email_service and summaries:
        try:
            LOGGER.info(
                "Attempting to send email to %s via SMTP (host inferred from %s)",
                email_service.config.smtp_recipient,
                email_service.config.smtp_sender,
            )
            email_service.send_summary_email(latest["title"], summaries)
            LOGGER.info("Email sent successfully")
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Failed to send summary email: %s", exc)
    elif email_service and not summaries:
        LOGGER.warning("Email service available but no summaries to send")
    elif not email_service:
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
        config.state_file,
        summarizer=summarizer,
        email_service=email_service,
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
            config.state_file,
            summarizer=summarizer,
            email_service=email_service,
        )
        LOGGER.info("Sleeping for %s seconds", config.poll_interval_seconds)
        time.sleep(config.poll_interval_seconds)


def main() -> None:
    """CLI entry point for the YouTube transcription automation."""
    parser = argparse.ArgumentParser(description="Poll YouTube channel for new videos")
    parser.add_argument(
        "--mode",
        choices=["once", "loop"],
        default="once",
        help="Run once or continuously",
    )
    args = parser.parse_args()

    if args.mode == "loop":
        config = load_config()
        run_loop(config)
    else:
        run_once()


if __name__ == "__main__":
    main()

