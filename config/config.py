# config/config.py
"""Configuration management with support for AWS services and local development."""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Import AWS services only when needed to avoid import errors in non-AWS environments
try:
    from src.core.aws_services import S3StateManager, SecretsManagerClient
except ImportError:
    S3StateManager = None  # type: ignore
    SecretsManagerClient = None  # type: ignore


@dataclass
class Config:
    """Application configuration hydrated from environment variables or AWS Secrets Manager."""

    youtube_api_key: str
    youtube_channel_handle: str
    openai_api_key: Optional[str] = None
    poll_interval_seconds: int = 900
    downloads_dir: Path = Path("downloads")
    state_file: Path = Path("last_video_id.json")
    whisper_model: str = "whisper-1"
    summary_model: str = "meta-llama/Llama-3.1-8B-Instruct"
    hf_token: Optional[str] = None
    email_enabled: bool = False
    smtp_port: int = 587
    smtp_password: Optional[str] = None
    smtp_sender: Optional[str] = None
    smtp_recipient: Optional[str] = None
    # AWS-specific configuration
    aws_region: Optional[str] = None
    s3_state_bucket: Optional[str] = None
    secrets_manager_secret_name: Optional[str] = None
    use_aws: bool = False

    def __post_init__(self) -> None:
        """Configure downloads directory for Lambda environment if detected."""
        # Lambda provides /tmp as the only writable directory
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            self.downloads_dir = Path("/tmp/downloads")

    def require_email_settings(self) -> None:
        """Validate SMTP configuration when email delivery is enabled."""

        if not self.email_enabled:
            return
        required_fields = {
            "smtp_password": self.smtp_password,
            "smtp_sender": self.smtp_sender,
            "smtp_recipient": self.smtp_recipient,
        }
        missing = [field for field, value in required_fields.items() if not value]
        if missing:
            raise ValueError(
                "Email summaries enabled, but missing SMTP fields: "
                + ", ".join(missing)
            )

    def ensure_directories(self) -> None:
        """Create download directory if it does not exist."""

        self.downloads_dir.mkdir(parents=True, exist_ok=True)


def _load_state_file(path: Path) -> Dict[str, Any]:
    """Load persisted metadata about the last processed video from local filesystem.

    Args:
        path: Location of the JSON persistence file.

    Returns:
        Deserialized JSON payload. Returns an empty dictionary when missing or invalid.

    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_secrets_from_aws(secret_name: str, region: Optional[str]) -> Dict[str, str]:
    """Load secrets from AWS Secrets Manager.

    Args:
        secret_name: Name or ARN of the secret in Secrets Manager.
        region: AWS region.

    Returns:
        Dictionary containing secret values.

    Raises:
        ValueError: If Secrets Manager client is not available or secret retrieval fails.

    """
    if SecretsManagerClient is None:
        raise ValueError(
            "boto3 not installed. Install it with: pip install boto3"
        )
    try:
        client = SecretsManagerClient(region=region)
        return client.get_secret(secret_name)
    except Exception as exc:
        raise ValueError(f"Failed to load secrets from AWS Secrets Manager: {exc}") from exc


def _determine_aws_usage() -> bool:
    """Determine if AWS services should be used based on environment.

    Returns:
        True if AWS environment variables are set, False otherwise.

    """
    return bool(
        os.getenv("S3_STATE_BUCKET") or os.getenv("SECRETS_MANAGER_SECRET_NAME")
    )


def load_config() -> Config:
    """Load configuration from environment variables, AWS Secrets Manager, or .env file.

    Configuration priority:
    1. AWS Secrets Manager (if SECRETS_MANAGER_SECRET_NAME is set)
    2. Environment variables
    3. .env file (for local development)

    Returns:
        A fully populated :class:`Config` instance.

    Raises:
        ValueError: If required configuration is missing.

    Example:
        >>> config = load_config()
        >>> config.downloads_dir.exists()
        True

    """
    # Load .env file for local development (will be overridden by environment variables)
    load_dotenv()

    # Determine if we should use AWS services
    use_aws = _determine_aws_usage()
    aws_region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    s3_state_bucket = os.getenv("S3_STATE_BUCKET")
    secrets_manager_secret_name = os.getenv("SECRETS_MANAGER_SECRET_NAME")

    # Load secrets from AWS Secrets Manager if configured
    secrets: Dict[str, str] = {}
    if use_aws and secrets_manager_secret_name:
        try:
            secrets = _load_secrets_from_aws(secrets_manager_secret_name, aws_region)
        except Exception as exc:
            raise ValueError(
                f"Failed to load secrets from AWS Secrets Manager: {exc}"
            ) from exc

    # Load configuration values (AWS secrets take precedence over env vars)
    youtube_api_key = secrets.get("YOUTUBE_API_KEY") or os.getenv("YOUTUBE_API_KEY")
    youtube_channel_handle = (
        secrets.get("YOUTUBE_CHANNEL_HANDLE") or os.getenv("YOUTUBE_CHANNEL_HANDLE")
    )
    openai_api_key = secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    hf_token = secrets.get("HF_TOKEN") or os.getenv("HF_TOKEN")
    smtp_password = secrets.get("SMTP_PASSWORD") or os.getenv("SMTP_PASSWORD")
    smtp_sender = secrets.get("SMTP_SENDER") or os.getenv("SMTP_SENDER")
    smtp_recipient = secrets.get("SMTP_RECIPIENT") or os.getenv("SMTP_RECIPIENT")

    # Validate required fields
    missing = [
        name
        for name, value in [
            ("YOUTUBE_API_KEY", youtube_api_key),
            ("YOUTUBE_CHANNEL_HANDLE", youtube_channel_handle),
        ]
        if not value
    ]
    if missing:
        raise ValueError(
            "Missing required configuration: " + ", ".join(missing)
        )

    # Load optional configuration
    poll_interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "900"))
    downloads_dir_str = os.getenv("DOWNLOADS_DIR")
    downloads_dir = Path(downloads_dir_str) if downloads_dir_str else Path("downloads")
    # Lambda environment uses /tmp
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        downloads_dir = Path("/tmp/downloads")
    state_file = Path(os.getenv("STATE_FILE", "last_video_id.json"))
    whisper_model = os.getenv("WHISPER_MODEL", "whisper-1")
    summary_model = os.getenv("SUMMARY_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    email_enabled = os.getenv("EMAIL_SUMMARIES_ENABLED", "false").lower() == "true"
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    config = Config(
        youtube_api_key=youtube_api_key,
        youtube_channel_handle=youtube_channel_handle,
        openai_api_key=openai_api_key,
        poll_interval_seconds=poll_interval_seconds,
        downloads_dir=downloads_dir,
        state_file=state_file,
        whisper_model=whisper_model,
        summary_model=summary_model,
        hf_token=hf_token,
        email_enabled=email_enabled,
        smtp_port=smtp_port,
        smtp_password=smtp_password,
        smtp_sender=smtp_sender,
        smtp_recipient=smtp_recipient,
        aws_region=aws_region,
        s3_state_bucket=s3_state_bucket,
        secrets_manager_secret_name=secrets_manager_secret_name,
        use_aws=use_aws,
    )
    config.ensure_directories()
    config.require_email_settings()
    return config


def load_last_video_id(config: Config) -> Optional[str]:
    """Return the last processed video id from S3 or local filesystem.

    Args:
        config: Configuration object containing AWS and filesystem settings.

    Returns:
        Last processed video ID, or None if not found.

    Raises:
        ValueError: If S3 is configured but state manager is unavailable.

    """
    # Use S3 if configured
    if config.use_aws and config.s3_state_bucket:
        if S3StateManager is None:
            raise ValueError(
                "S3 state bucket configured but boto3 not installed. "
                "Install it with: pip install boto3"
            )
        try:
            s3_manager = S3StateManager(
                bucket_name=config.s3_state_bucket, region=config.aws_region
            )
            state_data = s3_manager.load_state()
            return state_data.get("last_video_id")
        except Exception as exc:
            # Log error but fall back to local filesystem if S3 fails
            import logging

            logging.getLogger(__name__).warning(
                "Failed to load state from S3, falling back to local: %s", exc
            )
            return _load_state_file(config.state_file).get("last_video_id")

    # Fall back to local filesystem
    return _load_state_file(config.state_file).get("last_video_id")


def save_last_video_id(config: Config, video_id: str, title: str = "") -> None:
    """Persist the last processed video id and optional transcript metadata to S3 or local filesystem.

    Args:
        config: Configuration object containing AWS and filesystem settings.
        video_id: Video ID to save.
        title: Optional video title to save.

    Raises:
        ValueError: If S3 is configured but state manager is unavailable.

    """
    data: Dict[str, Any] = {
        "last_video_id": video_id,
        "last_video_title": title or "",
    }

    # Use S3 if configured
    if config.use_aws and config.s3_state_bucket:
        if S3StateManager is None:
            raise ValueError(
                "S3 state bucket configured but boto3 not installed. "
                "Install it with: pip install boto3"
            )
        try:
            s3_manager = S3StateManager(
                bucket_name=config.s3_state_bucket, region=config.aws_region
            )
            s3_manager.save_state(data)
            return
        except Exception as exc:
            # Log error but fall back to local filesystem if S3 fails
            import logging

            logging.getLogger(__name__).warning(
                "Failed to save state to S3, falling back to local: %s", exc
            )
            # Continue to local filesystem fallback

    # Fall back to local filesystem
    config.state_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

