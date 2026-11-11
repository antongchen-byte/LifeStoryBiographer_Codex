"""Transactional outbox: delivery is at-least-once if SMTP acknowledgement is lost."""
import logging
import smtplib
import ssl
from urllib.parse import urlsplit
from datetime import timedelta
from email.message import EmailMessage
from sqlalchemy import select
from ..config import get_settings
from ..database import SessionLocal
from ..models import OwnerNotification, User, now


def enqueue(db, owner_id, project_id, event_key):
    db.add(OwnerNotification(owner_id=owner_id, project_id=project_id, event_key=event_key))


def deliver_pending():
    settings = get_settings()
    if not (settings.smtp_host and settings.smtp_from and settings.notification_base_url):
        return
    if settings.smtp_username and not settings.smtp_password:
        return
    base = settings.notification_base_url.rstrip("/")
    url = urlsplit(base)
    if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"}):
        return
    # Row locks prevent concurrent workers sending the same queued event.
    with SessionLocal() as db:
        rows = list(db.scalars(select(OwnerNotification).where(
            OwnerNotification.sent_at.is_(None), OwnerNotification.next_attempt_at <= now()
        ).order_by(OwnerNotification.next_attempt_at).limit(5).with_for_update(skip_locked=True)))
        for row in rows:
            owner = db.get(User, row.owner_id)
            message = EmailMessage()
            message["From"] = settings.smtp_from
            message["To"] = owner.email
            message["Subject"] = "Your Editor has shared new content"
            message["Message-ID"] = f"<editor-{row.id}@{settings.smtp_from.rsplit('@', 1)[-1]}>"
            message.set_content("Your Production Editor has shared new content with you. "
                "Sign in with your registered account to review it.\n\n"
                f"{base}/projects/{row.project_id}\n\n"
                "Your original work remains unchanged.\n")
            row.attempts += 1
            try:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    if settings.smtp_username:
                        smtp.login(settings.smtp_username, settings.smtp_password)
                    smtp.send_message(message)
                row.sent_at = now()
            except Exception as error:
                row.next_attempt_at = now() + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
                logging.getLogger(__name__).warning("Owner email deferred (%s)", type(error).__name__)
        db.commit()
