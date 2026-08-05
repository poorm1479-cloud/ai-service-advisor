"""Transactional email sender (fake | smtp)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.infrastructure.config import settings

logger = logging.getLogger("asa.email")

_sent: list[dict[str, str]] = []


def get_sent_emails() -> list[dict[str, str]]:
    return list(_sent)


def clear_sent_emails() -> None:
    _sent.clear()


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class FakeEmailSender:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        _sent.append({"to": to, "subject": subject, "body": body})
        logger.info("email.fake to=%s subject=%s", to, subject)


class SmtpEmailSender:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = settings.smtp_from_email
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("email.smtp to=%s subject=%s", to, subject)


def build_email_sender() -> EmailSender:
    if (settings.email_provider or "fake").lower() == "smtp":
        return SmtpEmailSender()
    return FakeEmailSender()
