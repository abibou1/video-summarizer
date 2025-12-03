# config/config.py
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration hydrated from environment variables."""

    youtube_api_key: str
    youtube_channel_handle: str
    openai_api_key: Optional[str] = None
    poll_interval_seconds: int = 900
    downloads_dir: Path = Path("downloads")
    state_file: Path = Path("last_video_id.json")
    whisper_model: str = "whisper-1"
    summary_model: str = "meta-llama/Llama-3.1-8B-Instruct"
    hf_token: Optional[str] = None
    use_quantization: bool = True
    device: str = "auto"
    email_enabled: bool = False
    smtp_port: int = 587
    smtp_password: Optional[str] = None
    smtp_sender: Optional[str] = None
    smtp_recipient: Optional[str] = None

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
    """Load persisted metadata about the last processed video.

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


def load_config() -> Config:
    """Load configuration from the environment and ensure necessary folders exist.

    Returns:
        A fully populated :class:`Config` instance.

    Raises:
        ValueError: If required environment variables are missing.

    Example:
        >>> config = load_config()
        >>> config.downloads_dir.exists()
        True

    """
    load_dotenv()

    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    youtube_channel_handle = os.getenv("YOUTUBE_CHANNEL_HANDLE")
    openai_api_key = os.getenv("OPENAI_API_KEY")

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
            "Missing required environment variables: " + ", ".join(missing)
        )

    poll_interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "900"))
    downloads_dir = Path(os.getenv("DOWNLOADS_DIR", "downloads"))
    state_file = Path(os.getenv("STATE_FILE", "last_video_id.json"))
    whisper_model = os.getenv("WHISPER_MODEL", "whisper-1")
    summary_model = os.getenv("SUMMARY_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
    hf_token = os.getenv("HF_TOKEN")
    use_quantization = os.getenv("USE_QUANTIZATION", "true").lower() == "true"
    device = os.getenv("DEVICE", "auto")
    email_enabled = os.getenv("EMAIL_SUMMARIES_ENABLED", "false").lower() == "true"
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_sender = os.getenv("SMTP_SENDER")
    smtp_recipient = os.getenv("SMTP_RECIPIENT")

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
        use_quantization=use_quantization,
        device=device,
        email_enabled=email_enabled,
        smtp_port=smtp_port,
        smtp_password=smtp_password,
        smtp_sender=smtp_sender,
        smtp_recipient=smtp_recipient,
    )
    config.ensure_directories()
    config.require_email_settings()
    return config


def load_last_video_id(path: Path) -> Optional[str]:
    """Return the last processed video id from disk."""

    return _load_state_file(path).get("last_video_id")


def save_last_video_id(path: Path, video_id: str, title: str = "") -> None:
    """Persist the last processed video id and optional transcript metadata."""

    data: Dict[str, Any] = {
        "last_video_id": video_id,
        "last_video_title": title or "",
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

