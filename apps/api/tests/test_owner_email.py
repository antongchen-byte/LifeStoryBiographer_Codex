from contextlib import nullcontext
from types import SimpleNamespace
from sqlalchemy import select
from app.models import OwnerNotification, User, now
from app.services import owner_email


def test_delivery_retry_and_registered_recipient(db, owner, project, monkeypatch):
    recipient = db.scalar(select(User))
    owner_email.enqueue(db, recipient.id, project, "review:test")
    db.commit()
    settings = SimpleNamespace(smtp_host="smtp.gmail.com", smtp_port=587,
        smtp_from="antongchen@gmail.com", smtp_username="sender", smtp_password="fixture",
        notification_base_url="https://example.com")
    monkeypatch.setattr(owner_email, "get_settings", lambda: settings)
    monkeypatch.setattr(owner_email, "SessionLocal", lambda: nullcontext(db))
    messages = []
    class SMTP:
        fail = True
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, **kwargs): pass
        def login(self, *args): pass
        def send_message(self, message):
            if self.fail: raise OSError("temporary failure")
            messages.append(message)
    monkeypatch.setattr(owner_email.smtplib, "SMTP", SMTP)
    owner_email.deliver_pending()
    row = db.scalar(select(OwnerNotification))
    assert row.sent_at is None and row.attempts == 1
    SMTP.fail = False
    row.next_attempt_at = now()
    db.commit()
    owner_email.deliver_pending()
    owner_email.deliver_pending()
    assert len(messages) == 1
    assert messages[0]["To"] == recipient.email
    assert f"https://example.com/projects/{project}" in messages[0].get_content()
    assert row.sent_at is not None
