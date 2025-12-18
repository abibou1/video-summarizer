# src/services/email_service.py
from __future__ import annotations

import html
import logging
import smtplib
from email.message import EmailMessage
from typing import Tuple

from config.config import Config
from src.services.summarizer import SummaryBundle

LOGGER = logging.getLogger(__name__)


class EmailService:
    """Send transcript summaries over SMTP with TLS support."""

    def __init__(self, config: Config):
        self.config = config

    def _resolve_smtp_target(self) -> Tuple[str, int]:
        """Infer SMTP host/port from the sender address and config."""

        assert self.config.smtp_sender is not None  # validated earlier
        sender_domain = self.config.smtp_sender.split("@")[-1]
        host = f"smtp.{sender_domain}"
        return host, self.config.smtp_port

    def _build_email(
        self,
        video_title: str,
        summaries: SummaryBundle,
    ) -> EmailMessage:
        """Create a multipart email payload containing both summaries."""

        msg = EmailMessage()
        msg["Subject"] = f"Video summary: {video_title}"
        msg["From"] = self.config.smtp_sender
        msg["To"] = self.config.smtp_recipient

        plain_body = self._format_plain_text(video_title, summaries)
        html_body = self._format_html_body(video_title, summaries)

        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        return msg

    def send_summary_email(self, video_title: str, summaries: SummaryBundle) -> None:
        """Send the summary email and log delivery status."""

        if not self.config.email_enabled:
            LOGGER.warning("Email delivery disabled; skipping SMTP send.")
            return

        assert self.config.smtp_sender is not None
        assert self.config.smtp_recipient is not None

        message = self._build_email(video_title, summaries)
        host, port = self._resolve_smtp_target()

        assert self.config.smtp_password is not None

        LOGGER.info("Connecting to SMTP server %s:%d", host, port)
        try:
            with smtplib.SMTP(host, port, timeout=30) as client:
                LOGGER.debug("SMTP connection established, starting TLS")
                client.starttls()
                LOGGER.debug("TLS started, attempting login as %s", self.config.smtp_sender)
                client.login(self.config.smtp_sender, self.config.smtp_password)
                LOGGER.debug("Login successful, sending message")
                client.send_message(message)
                LOGGER.debug("Message sent successfully")
        except smtplib.SMTPAuthenticationError as exc:
            LOGGER.error(
                "SMTP authentication failed. Check username (%s) and password.",
                self.config.smtp_sender,
            )
            raise RuntimeError("SMTP authentication failed.") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            LOGGER.error(
                "SMTP recipient refused: %s. Check recipient address.",
                self.config.smtp_recipient,
            )
            raise RuntimeError("SMTP recipient refused.") from exc
        except smtplib.SMTPServerDisconnected as exc:
            LOGGER.error("SMTP server disconnected unexpectedly.")
            raise RuntimeError("SMTP server disconnected.") from exc
        except smtplib.SMTPException as exc:
            LOGGER.exception("SMTP error occurred: %s", exc)
            raise RuntimeError(f"SMTP delivery failed: {exc}") from exc
        except OSError as exc:
            LOGGER.error(
                "Network error connecting to SMTP server %s:%d: %s",
                host,
                port,
                exc,
            )
            raise RuntimeError(f"Failed to connect to SMTP server: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Unexpected error sending email: %s", exc)
            raise RuntimeError(f"Unexpected error sending email: {exc}") from exc

        LOGGER.info(
            "Summary email delivered to %s for video '%s'.",
            self.config.smtp_recipient,
            video_title,
        )

    def _format_plain_text(
        self,
        video_title: str,
        summaries: SummaryBundle,
    ) -> str:
        """Return the plain-text portion of the summary email."""

        return (
            f"Summaries for: {video_title}\n\n"
            f"Short summary:\n{summaries['short_summary']}\n\n"
            f"Comprehensive summary:\n{summaries['comprehensive_summary']}\n"
        )

    def _format_html_body(
        self,
        video_title: str,
        summaries: SummaryBundle,
    ) -> str:
        """Return a simple HTML representation of the summaries."""

        short_html = html.escape(summaries["short_summary"])
        comprehensive_html = html.escape(summaries["comprehensive_summary"]).replace(
            "\n", "<br/>"
        )
        safe_title = html.escape(video_title)
        return f"""
        <html>
            <body>
                <h2>Summaries for: {safe_title}</h2>
                <h3>Short summary</h3>
                <p>{short_html}</p>
                <h3>Comprehensive summary</h3>
                <p>{comprehensive_html}</p>
            </body>
        </html>
        """

    def send_error_email(self, video_title: str, error_reason: str) -> None:
        """Send an error notification email explaining why summaries were not generated.

        Args:
            video_title: Title of the video that failed to process.
            error_reason: Human-readable explanation of why summaries were not generated.

        """
        if not self.config.email_enabled:
            LOGGER.warning("Email delivery disabled; skipping SMTP send.")
            return

        assert self.config.smtp_sender is not None
        assert self.config.smtp_recipient is not None

        message = self._build_error_email(video_title, error_reason)
        host, port = self._resolve_smtp_target()

        assert self.config.smtp_password is not None

        LOGGER.info("Connecting to SMTP server %s:%d", host, port)
        try:
            with smtplib.SMTP(host, port, timeout=30) as client:
                LOGGER.debug("SMTP connection established, starting TLS")
                client.starttls()
                LOGGER.debug("TLS started, attempting login as %s", self.config.smtp_sender)
                client.login(self.config.smtp_sender, self.config.smtp_password)
                LOGGER.debug("Login successful, sending error message")
                client.send_message(message)
                LOGGER.debug("Error message sent successfully")
        except smtplib.SMTPAuthenticationError as exc:
            LOGGER.error(
                "SMTP authentication failed. Check username (%s) and password.",
                self.config.smtp_sender,
            )
            raise RuntimeError("SMTP authentication failed.") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            LOGGER.error(
                "SMTP recipient refused: %s. Check recipient address.",
                self.config.smtp_recipient,
            )
            raise RuntimeError("SMTP recipient refused.") from exc
        except smtplib.SMTPServerDisconnected as exc:
            LOGGER.error("SMTP server disconnected unexpectedly.")
            raise RuntimeError("SMTP server disconnected.") from exc
        except smtplib.SMTPException as exc:
            LOGGER.exception("SMTP error occurred: %s", exc)
            raise RuntimeError(f"SMTP delivery failed: {exc}") from exc
        except OSError as exc:
            LOGGER.error(
                "Network error connecting to SMTP server %s:%d: %s",
                host,
                port,
                exc,
            )
            raise RuntimeError(f"Failed to connect to SMTP server: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Unexpected error sending error email: %s", exc)
            raise RuntimeError(f"Unexpected error sending error email: {exc}") from exc

        LOGGER.info(
            "Error notification email delivered to %s for video '%s'.",
            self.config.smtp_recipient,
            video_title,
        )

    def _build_error_email(
        self,
        video_title: str,
        error_reason: str,
    ) -> EmailMessage:
        """Create an error notification email payload.

        Args:
            video_title: Title of the video that failed to process.
            error_reason: Human-readable explanation of why summaries were not generated.

        Returns:
            EmailMessage configured with error notification content.

        """
        msg = EmailMessage()
        msg["Subject"] = f"Error generating video summary: {video_title}"
        msg["From"] = self.config.smtp_sender
        msg["To"] = self.config.smtp_recipient

        plain_body = self._format_error_plain_text(video_title, error_reason)
        html_body = self._format_error_html_body(video_title, error_reason)

        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        return msg

    def _format_error_plain_text(
        self,
        video_title: str,
        error_reason: str,
    ) -> str:
        """Return the plain-text portion of the error notification email.

        Args:
            video_title: Title of the video that failed to process.
            error_reason: Human-readable explanation of why summaries were not generated.

        Returns:
            Plain text email body.

        """
        return (
            f"Error generating summaries for: {video_title}\n\n"
            f"Reason: {error_reason}\n\n"
            "Please check the logs for more details."
        )

    def _format_error_html_body(
        self,
        video_title: str,
        error_reason: str,
    ) -> str:
        """Return an HTML representation of the error notification email.

        Args:
            video_title: Title of the video that failed to process.
            error_reason: Human-readable explanation of why summaries were not generated.

        Returns:
            HTML email body.

        """
        safe_title = html.escape(video_title)
        safe_reason = html.escape(error_reason).replace("\n", "<br/>")
        return f"""
        <html>
            <body>
                <h2>Error generating summaries for: {safe_title}</h2>
                <h3>Reason</h3>
                <p>{safe_reason}</p>
                <p><em>Please check the logs for more details.</em></p>
            </body>
        </html>
        """

    def send_no_new_videos_email(self, last_video_title: str | None = None) -> None:
        """Send a notification email when no new videos are detected since last check.

        Args:
            last_video_title: Title of the last processed video, if available.

        """
        if not self.config.email_enabled:
            LOGGER.warning("Email delivery disabled; skipping SMTP send.")
            return

        assert self.config.smtp_sender is not None
        assert self.config.smtp_recipient is not None

        message = self._build_no_new_videos_email(last_video_title)
        host, port = self._resolve_smtp_target()

        assert self.config.smtp_password is not None

        LOGGER.info("Connecting to SMTP server %s:%d", host, port)
        try:
            with smtplib.SMTP(host, port, timeout=30) as client:
                LOGGER.debug("SMTP connection established, starting TLS")
                client.starttls()
                LOGGER.debug("TLS started, attempting login as %s", self.config.smtp_sender)
                client.login(self.config.smtp_sender, self.config.smtp_password)
                LOGGER.debug("Login successful, sending no new videos notification")
                client.send_message(message)
                LOGGER.debug("No new videos notification sent successfully")
        except smtplib.SMTPAuthenticationError as exc:
            LOGGER.error(
                "SMTP authentication failed. Check username (%s) and password.",
                self.config.smtp_sender,
            )
            raise RuntimeError("SMTP authentication failed.") from exc
        except smtplib.SMTPRecipientsRefused as exc:
            LOGGER.error(
                "SMTP recipient refused: %s. Check recipient address.",
                self.config.smtp_recipient,
            )
            raise RuntimeError("SMTP recipient refused.") from exc
        except smtplib.SMTPServerDisconnected as exc:
            LOGGER.error("SMTP server disconnected unexpectedly.")
            raise RuntimeError("SMTP server disconnected.") from exc
        except smtplib.SMTPException as exc:
            LOGGER.exception("SMTP error occurred: %s", exc)
            raise RuntimeError(f"SMTP delivery failed: {exc}") from exc
        except OSError as exc:
            LOGGER.error(
                "Network error connecting to SMTP server %s:%d: %s",
                host,
                port,
                exc,
            )
            raise RuntimeError(f"Failed to connect to SMTP server: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Unexpected error sending no new videos email: %s", exc)
            raise RuntimeError(f"Unexpected error sending no new videos email: {exc}") from exc

        LOGGER.info(
            "No new videos notification email delivered to %s.",
            self.config.smtp_recipient,
        )

    def _build_no_new_videos_email(
        self,
        last_video_title: str | None = None,
    ) -> EmailMessage:
        """Create a no new videos notification email payload.

        Args:
            last_video_title: Title of the last processed video, if available.

        Returns:
            EmailMessage configured with no new videos notification content.

        """
        msg = EmailMessage()
        msg["Subject"] = "No new videos since last check"
        msg["From"] = self.config.smtp_sender
        msg["To"] = self.config.smtp_recipient

        plain_body = self._format_no_new_videos_plain_text(last_video_title)
        html_body = self._format_no_new_videos_html_body(last_video_title)

        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        return msg

    def _format_no_new_videos_plain_text(
        self,
        last_video_title: str | None = None,
    ) -> str:
        """Return the plain-text portion of the no new videos notification email.

        Args:
            last_video_title: Title of the last processed video, if available.

        Returns:
            Plain text email body.

        """
        if last_video_title:
            return (
                "No new videos since last check.\n\n"
                f"Last processed video: {last_video_title}\n\n"
                "The system will continue monitoring for new uploads."
            )
        return (
            "No new videos since last check.\n\n"
            "The system will continue monitoring for new uploads."
        )

    def _format_no_new_videos_html_body(
        self,
        last_video_title: str | None = None,
    ) -> str:
        """Return an HTML representation of the no new videos notification email.

        Args:
            last_video_title: Title of the last processed video, if available.

        Returns:
            HTML email body.

        """
        if last_video_title:
            safe_title = html.escape(last_video_title)
            return f"""
        <html>
            <body>
                <h2>No new videos since last check</h2>
                <p>Last processed video: <strong>{safe_title}</strong></p>
                <p><em>The system will continue monitoring for new uploads.</em></p>
            </body>
        </html>
        """
        return """
        <html>
            <body>
                <h2>No new videos since last check</h2>
                <p><em>The system will continue monitoring for new uploads.</em></p>
            </body>
        </html>
        """

