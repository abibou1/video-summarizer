# src/lambda_handler.py
"""AWS Lambda handler for YouTube video transcription automation."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Add project root to Python path to allow imports of config and src modules
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config.config import Config, load_config, load_last_video_id, save_last_video_id
from src.services.email_service import EmailService
from src.services.summarizer import TranscriptSummarizer
from src.services.transcriber import WhisperTranscriber
from src.services.youtube_poller import YouTubePoller

# Configure logging for Lambda (CloudWatch Logs)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
LOGGER = logging.getLogger(__name__)


def process_latest_video(
    config: Config,
    poller: YouTubePoller,
    transcriber: WhisperTranscriber,
    summarizer: TranscriptSummarizer | None = None,
    email_service: EmailService | None = None,
) -> Dict[str, Any]:
    """Process the latest video from the YouTube channel.

    Args:
        config: Application configuration.
        poller: Component responsible for discovering YouTube uploads.
        transcriber: Component responsible for downloading audio and invoking Whisper.
        summarizer: Optional component that generates summaries for the transcript.
        email_service: Optional component responsible for emailing summaries.

    Returns:
        Dictionary containing execution results and metadata.

    """
    result: Dict[str, Any] = {
        "success": False,
        "video_id": None,
        "video_title": None,
        "transcript_length": 0,
        "summaries_generated": False,
        "email_sent": False,
        "message": "",
    }

    try:
        last_video_id = load_last_video_id(config)
        LOGGER.info("Last processed video ID: %s", last_video_id)

        latest = poller.fetch_latest_video()
        if not latest:
            result["message"] = "No videos found in channel"
            LOGGER.info(result["message"])
            return result

        if latest["video_id"] == last_video_id:
            result["message"] = "No new videos since last check"
            result["success"] = True  # This is a successful check, not an error
            LOGGER.info(result["message"])
            return result

        LOGGER.info("New video detected: %s (ID: %s)", latest["title"], latest["video_id"])
        result["video_id"] = latest["video_id"]
        result["video_title"] = latest["title"]

        # Transcribe video
        transcript = transcriber.transcribe(latest["video_id"])
        result["transcript_length"] = len(transcript)
        LOGGER.info("Transcript generated: %d characters", result["transcript_length"])

        # Save state
        save_last_video_id(config, latest["video_id"], title=latest["title"])
        LOGGER.info("State saved successfully")

        # Generate summaries if enabled
        summaries = None
        if summarizer:
            try:
                summaries = summarizer.generate_summaries(transcript)
                result["summaries_generated"] = True
                LOGGER.info("Summaries generated successfully")
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Failed to generate summaries: %s", exc)
                result["message"] = f"Failed to generate summaries: {exc}"

        # Send email if enabled and summaries available
        if email_service and summaries:
            try:
                LOGGER.info(
                    "Attempting to send email to %s via SMTP (host inferred from %s)",
                    email_service.config.smtp_recipient,
                    email_service.config.smtp_sender,
                )
                email_service.send_summary_email(latest["title"], summaries)
                result["email_sent"] = True
                LOGGER.info("Email sent successfully")
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Failed to send email: %s", exc)
                result["message"] = f"Failed to send email: {exc}"
        elif email_service and not summaries:
            LOGGER.warning("Email service available but no summaries to send")

        result["success"] = True
        if not result["message"]:
            result["message"] = f"Successfully processed video: {latest['title']}"

    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Error processing video: %s", exc)
        result["message"] = f"Error: {str(exc)}"
        result["success"] = False

    return result


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler entry point.

    This function is invoked by AWS Lambda when triggered by EventBridge or other sources.
    It processes the latest video from a configured YouTube channel.

    Args:
        event: Lambda event data (EventBridge scheduled event or test event).
        context: Lambda context object (runtime information).

    Returns:
        Dictionary containing execution results suitable for CloudWatch Logs.

    Example:
        EventBridge scheduled event:
        {
            "version": "0",
            "id": "...",
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            ...
        }

    """
    request_id = getattr(context, "aws_request_id", getattr(context, "request_id", "unknown"))
    LOGGER.info("Lambda function invoked. Request ID: %s", request_id)
    LOGGER.debug("Event data: %s", json.dumps(event, default=str))

    try:
        # Load configuration (from environment variables and/or Secrets Manager)
        config = load_config()
        LOGGER.info("Configuration loaded. AWS mode: %s", config.use_aws)
        if config.use_aws:
            LOGGER.info(
                "AWS configuration - Region: %s, S3 Bucket: %s, Secret: %s",
                config.aws_region,
                config.s3_state_bucket,
                config.secrets_manager_secret_name,
            )

        # Initialize services
        LOGGER.info("Initializing services...")
        poller = YouTubePoller(config)
        transcriber = WhisperTranscriber(config)
        summarizer = TranscriptSummarizer(config) if config.email_enabled else None
        email_service = EmailService(config) if config.email_enabled else None

        LOGGER.info("Email enabled: %s", config.email_enabled)
        if config.email_enabled:
            LOGGER.info(
                "Email configuration - Sender: %s, Recipient: %s, Port: %d",
                config.smtp_sender,
                config.smtp_recipient,
                config.smtp_port,
            )

        # Process latest video
        result = process_latest_video(
            config=config,
            poller=poller,
            transcriber=transcriber,
            summarizer=summarizer,
            email_service=email_service,
        )

        # Log result
        LOGGER.info("Processing completed. Success: %s", result["success"])
        LOGGER.info("Result: %s", json.dumps(result, indent=2))

        # Return result for CloudWatch Logs
        return {
            "statusCode": 200 if result["success"] else 500,
            "body": json.dumps(result, indent=2),
        }

    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Fatal error in Lambda handler: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "success": False,
                    "message": f"Fatal error: {str(exc)}",
                    "error_type": type(exc).__name__,
                },
                indent=2,
            ),
        }

