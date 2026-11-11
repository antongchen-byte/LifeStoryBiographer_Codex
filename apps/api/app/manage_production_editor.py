"""Local operator tool. Production permissions are never exposed through registration."""
import argparse
import getpass
from sqlalchemy import select
from .database import SessionLocal
from .models import User
from .services.auth import password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--create", action="store_true")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.casefold()))
        if not user:
            if not args.create or args.revoke:
                raise SystemExit("Account not found; use --create to provision it")
            password = getpass.getpass("New password (at least 10 characters): ")
            if not 10 <= len(password) <= 200:
                raise SystemExit("Password must be 10–200 characters")
            if password != getpass.getpass("Confirm password: "):
                raise SystemExit("Passwords do not match")
            user = User(email=args.email.casefold(), name="Production Editor", password_hash=password_hash(password))
            db.add(user)
        user.production_editor = not args.revoke
        db.commit()
        print("Production Editor access " + ("revoked" if args.revoke else "enabled"))


if __name__ == "__main__":
    main()
