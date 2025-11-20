import argparse
import logging
import time
from typing import Optional

from pathlib import Path

from config import load_config, load_last_video_id, save_last_video_id
from transcriber import WhisperTranscriber
from youtube_poller import YouTubePoller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


def process_latest_video(
    poller: YouTubePoller, transcriber: WhisperTranscriber, state_file: Path
) -> None:
    last_video_id = load_last_video_id(state_file)
    latest = poller.fetch_latest_video()
    if not latest:
        LOGGER.info("No videos found.")
        return
    if latest["video_id"] == last_video_id:
        LOGGER.info("No new videos since last check.")
        return

    LOGGER.info("New video detected: %s", latest["title"])
    transcript, transcript_path = transcriber.transcribe(
        latest["video_id"], latest["title"]
    )
    save_last_video_id(state_file, latest["video_id"])
    print(transcript)
    if transcript_path:
        LOGGER.info("Transcript saved to %s", transcript_path)
    LOGGER.debug("Transcript content:\n%s", transcript)


def run_once() -> None:
    config = load_config()
    poller = YouTubePoller(config)
    transcriber = WhisperTranscriber(config)
    process_latest_video(poller, transcriber, config.state_file)


def run_loop(config) -> None:
    poller = YouTubePoller(config)
    transcriber = WhisperTranscriber(config)
    while True:
        process_latest_video(poller, transcriber, config.state_file)
        LOGGER.info("Sleeping for %s seconds", config.poll_interval_seconds)
        time.sleep(config.poll_interval_seconds)


def main():
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

