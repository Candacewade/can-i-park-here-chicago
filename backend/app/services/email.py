"""Send an email via Gmail SMTP (app password), or -- with no credentials --
write it to the outbox for local development.
"""

from __future__ import annotations

import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    CHICAGO_TZ,
    GMAIL_APP_PASSWORD,
    GMAIL_SENDER,
    OUTBOX_DIR,
    SMTP_HOST,
    SMTP_PORT,
)


def send_email(to: str, subject: str, body_text: str, body_html: str | None = None) -> str:
    """Returns 'sent' or a filesystem path (when written to the outbox)."""
    if not (GMAIL_SENDER and GMAIL_APP_PASSWORD):
        return _to_outbox(to, subject, body_text)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        smtp.sendmail(GMAIL_SENDER, [to], msg.as_string())
    return "sent"


def _to_outbox(to: str, subject: str, body_text: str) -> str:
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=CHICAGO_TZ).strftime("%Y%m%dT%H%M%S")
    path = OUTBOX_DIR / f"{ts}_{to.replace('@', '_at_')}.txt"
    path.write_text(f"To: {to}\nSubject: {subject}\n\n{body_text}\n")
    return str(path)
