# config/__init__.py
"""Configuration module."""

from config.config import Config, load_config, load_last_video_id, save_last_video_id

__all__ = ["Config", "load_config", "load_last_video_id", "save_last_video_id"]

