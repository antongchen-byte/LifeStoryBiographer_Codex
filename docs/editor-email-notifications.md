# Editor sharing notifications

Sharing a new Editor version, approved clip set, or finished video queues an email to the project owner's registered email. The queue is committed in the same database transaction as the share. Repeating an already-completed share does not queue another notification. The background worker sends via authenticated SMTP with STARTTLS and retries failures with backoff. Emails contain a sign-in-protected project link, not private attachments. Delivery is at-least-once: a lost SMTP acknowledgement can cause a duplicate.

Sender: `antongchen@gmail.com`. Configure these values in local `.env` or the cloud `biographer-runtime-env` secret:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=antongchen@gmail.com
SMTP_FROM=antongchen@gmail.com
SMTP_PASSWORD=<Gmail app password>
NOTIFICATION_BASE_URL=https://lifestory-biographer-1019141557914.us-east1.run.app
```

Use a Gmail app password, not the LifeStory application password. Never commit credentials. Apply Alembic migration 0010 and recreate API/worker after setting environment values. A missing sender configuration leaves messages queued; it does not prevent sharing. Queued notifications will send when configuration is supplied. The worker must be running. SMTP acceptance does not guarantee inbox placement.

Inspect `owner_notifications` for pending messages, attempts, next_attempt_at, and sent_at; logs record exception type without credentials or message contents. Removing a project or account cascades its notification records. For local deployment use `NOTIFICATION_BASE_URL=http://localhost:3000`; such links only work on the local machine. Public deployment links require HTTPS.
