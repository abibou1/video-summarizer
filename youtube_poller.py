from __future__ import annotations

import logging
from typing import Dict, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Config

LOGGER = logging.getLogger(__name__)


class YouTubePoller:
    """Utility that resolves channel metadata and fetches the latest upload."""

    def __init__(self, config: Config):
        """Initialize the poller with an authenticated YouTube client."""

        self.config = config
        self.client = build("youtube", "v3", developerKey=config.youtube_api_key)
        self._channel_id: Optional[str] = None
        self._uploads_playlist: Optional[str] = None

    def _resolve_channel_id(self) -> str:
        """Convert a channel handle to a channel id via the Search API."""

        if self._channel_id:
            return self._channel_id
        handle = self.config.youtube_channel_handle.lstrip("@")
        try:
            response = (
                self.client.search()
                .list(q=handle, type="channel", maxResults=1, part="snippet")
                .execute()
            )
        except HttpError as exc:
            raise RuntimeError(f"Failed to resolve channel handle: {exc}") from exc

        items = response.get("items", [])
        if not items:
            raise RuntimeError(
                f"No channel found for handle {self.config.youtube_channel_handle}"
            )
        self._channel_id = items[0]["snippet"]["channelId"]
        return self._channel_id

    def _resolve_uploads_playlist(self) -> str:
        """Locate the uploads playlist that contains recent channel videos."""

        if self._uploads_playlist:
            return self._uploads_playlist
        channel_id = self._resolve_channel_id()
        try:
            response = (
                self.client.channels()
                .list(part="contentDetails", id=channel_id)
                .execute()
            )
        except HttpError as exc:
            raise RuntimeError(f"Failed to fetch channel details: {exc}") from exc

        items = response.get("items", [])
        if not items:
            raise RuntimeError("Channel details response missing items")

        self._uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        return self._uploads_playlist

    def fetch_latest_video(self) -> Optional[Dict[str, str]]:
        """Return metadata for the most recent upload if available."""

        playlist_id = self._resolve_uploads_playlist()
        try:
            response = (
                self.client.playlistItems()
                .list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=1,
                )
                .execute()
            )
        except HttpError as exc:
            LOGGER.error("Failed to fetch playlist items: %s", exc)
            return None

        items = response.get("items", [])
        if not items:
            return None

        item = items[0]
        snippet = item["snippet"]
        content_details = item["contentDetails"]
        return {
            "video_id": content_details["videoId"],
            "title": snippet.get("title", "Untitled"),
            "published_at": snippet.get("publishedAt"),
        }

