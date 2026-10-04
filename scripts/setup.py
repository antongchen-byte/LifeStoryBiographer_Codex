"""Create local environment settings without overwriting an existing .env."""
import secrets
from pathlib import Path
root = Path(__file__).resolve().parent.parent
path = root / ".env"
if path.exists():
    print("Existing .env preserved")
else:
    text = (root / ".env.example").read_text().replace("replace-with-at-least-32-random-characters", secrets.token_urlsafe(48))
    path.write_text(text)
    path.chmod(0o600)
    print("Created .env with a random authentication secret")
