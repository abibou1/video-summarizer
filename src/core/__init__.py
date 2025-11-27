# src/core/__init__.py
"""Core configuration and utilities."""

from src.core.config import Config, load_config, load_last_video_id, save_last_video_id

__all__ = ["Config", "load_config", "load_last_video_id", "save_last_video_id"]

