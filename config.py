import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Config:
    youtube_api_key: str
    youtube_channel_handle: str
    openai_api_key: str
    poll_interval_seconds: int = 900
    downloads_dir: Path = Path("downloads")
    transcripts_dir: Path = Path("transcripts")
    state_file: Path = Path("last_video_id.json")
    whisper_model: str = "whisper-1"

    def ensure_directories(self) -> None:
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)


def _load_state_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data.get("last_video_id")


def load_config() -> Config:
    load_dotenv()

    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    youtube_channel_handle = os.getenv("YOUTUBE_CHANNEL_HANDLE")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    missing = [
        name
        for name, value in [
            ("YOUTUBE_API_KEY", youtube_api_key),
            ("YOUTUBE_CHANNEL_HANDLE", youtube_channel_handle),
            ("OPENAI_API_KEY", openai_api_key),
        ]
        if not value
    ]
    if missing:
        raise ValueError(
            "Missing required environment variables: " + ", ".join(missing)
        )

    poll_interval_seconds = int(os.getenv("POLL_INTERVAL_SECONDS", "900"))
    downloads_dir = Path(os.getenv("DOWNLOADS_DIR", "downloads"))
    transcripts_dir = Path(os.getenv("TRANSCRIPTS_DIR", "transcripts"))
    state_file = Path(os.getenv("STATE_FILE", "last_video_id.json"))
    whisper_model = os.getenv("WHISPER_MODEL", "whisper-1")

    config = Config(
        youtube_api_key=youtube_api_key,
        youtube_channel_handle=youtube_channel_handle,
        openai_api_key=openai_api_key,
        poll_interval_seconds=poll_interval_seconds,
        downloads_dir=downloads_dir,
        transcripts_dir=transcripts_dir,
        state_file=state_file,
        whisper_model=whisper_model,
    )
    config.ensure_directories()
    return config


def load_last_video_id(path: Path) -> Optional[str]:
    return _load_state_file(path)


def save_last_video_id(path: Path, video_id: str) -> None:
    data = {"last_video_id": video_id}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

