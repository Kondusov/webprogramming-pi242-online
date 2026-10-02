from __future__ import annotations
import asyncio
import logging

import aiosmtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("mailer")


def _wrap(subject: str, content_html: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{subject}</title></head>
<body style="font-family:system-ui,sans-serif;background:#f0f2f5;padding:24px;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;">
    <h2 style="margin:0 0 16px;color:#222;">{subject}</h2>
    <div style="color:#333;font-size:15px;line-height:1.5;">{content_html}</div>
    <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
    <p style="color:#888;font-size:12px;margin:0;">Это автоматическое письмо.</p>
  </div>
</body></html>"""


async def send_mail(to: str, subject: str, html: str) -> bool:
    body = _wrap(subject, html)

    # Dev-режим: SMTP не настроен — печатаем в консоль
    if not settings.SMTP_HOST:
        log.warning("=" * 60)
        log.warning("DEV EMAIL → %s", to)
        log.warning("Subject: %s", subject)
        log.warning("%s", html)
        log.warning("=" * 60)
        return True

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("HTML письмо. Откройте в клиенте с поддержкой HTML.")
    msg.add_alternative(body, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_TLS,
            timeout=10,
        )
        return True
    except Exception as e:
        log.exception("Не удалось отправить письмо: %s", e)
        return False


async def send_verification_email(to: str, username: str, code: str) -> bool:
    content = f"""
        <p>Привет, <b>{username}</b>!</p>
        <p>Спасибо за регистрацию. Введите этот код, чтобы подтвердить email:</p>
        <p style="font-size:32px;font-weight:bold;letter-spacing:8px;
                  background:#eef2fb;color:#4a76f5;padding:16px;
                  border-radius:10px;text-align:center;margin:20px 0;">{code}</p>
        <p style="color:#666;font-size:13px;">Код действует 15 минут.</p>
    """
    return await send_mail(to, "Подтверждение email", content)


async def send_reset_email(to: str, username: str, code: str) -> bool:
    content = f"""
        <p>Привет, <b>{username}</b>!</p>
        <p>Вы запросили сброс пароля. Введите код:</p>
        <p style="font-size:32px;font-weight:bold;letter-spacing:8px;
                  background:#eef2fb;color:#4a76f5;padding:16px;
                  border-radius:10px;text-align:center;margin:20px 0;">{code}</p>
        <p style="color:#666;font-size:13px;">Код действует 15 минут.</p>
    """
    return await send_mail(to, "Сброс пароля", content)