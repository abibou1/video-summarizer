# tests/unit/test_email_service.py
from __future__ import annotations

import smtplib
from types import SimpleNamespace

import pytest

from config.config import Config
from src.services.email_service import EmailService
from src.services.summarizer import SummaryBundle


class _DummySMTP:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.started_tls = False
        self.logged_in = False
        self.sent_messages = []

    def __enter__(self) -> "_DummySMTP":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = True
        self.username = username
        self.password = password

    def send_message(self, message) -> None:
        self.sent_messages.append(message)


@pytest.fixture()
def config(tmp_path):
    return Config(
        youtube_api_key="key",
        youtube_channel_handle="@handle",
        openai_api_key="openai",
        downloads_dir=tmp_path / "downloads",
        state_file=tmp_path / "state.json",
        email_enabled=True,
        smtp_port=587,
        smtp_password="pass",
        smtp_sender="sender@example.com",
        smtp_recipient="recipient@example.com",
    )


def test_send_summary_email(monkeypatch, config):
    dummy_smtp = _DummySMTP()

    def _smtp_factory(*args, **kwargs):
        dummy_smtp.args = args
        dummy_smtp.kwargs = kwargs
        return dummy_smtp

    monkeypatch.setattr(smtplib, "SMTP", _smtp_factory)

    service = EmailService(config)
    summaries: SummaryBundle = {
        "short_summary": "Short text",
        "comprehensive_summary": "Detailed text",
    }
    service.send_summary_email("Video Title", summaries)

    assert dummy_smtp.args[0] == "smtp.example.com"
    assert dummy_smtp.kwargs.get("timeout") == 30
    assert dummy_smtp.started_tls
    assert dummy_smtp.logged_in
    assert dummy_smtp.sent_messages
    message = dummy_smtp.sent_messages[0]
    plain_part = message.get_body(preferencelist=("plain",))
    assert plain_part is not None
    assert "Short text" in plain_part.get_content()


def test_raises_runtime_error_on_failure(monkeypatch, config):
    class _ExplodingSMTP(_DummySMTP):
        def send_message(self, message) -> None:
            raise smtplib.SMTPException("boom")

    monkeypatch.setattr(smtplib, "SMTP", lambda *args, **kwargs: _ExplodingSMTP())

    service = EmailService(config)
    summaries: SummaryBundle = {
        "short_summary": "Short text",
        "comprehensive_summary": "Detailed text",
    }

    with pytest.raises(RuntimeError):
        service.send_summary_email("Video Title", summaries)

