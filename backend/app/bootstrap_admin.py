"""Promote the explicitly configured, already registered admin account."""
import os

from .auth import bootstrap_admin
from .database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        user = bootstrap_admin(os.getenv("ADMIN_BOOTSTRAP_EMAIL", ""), db)
        print(f"Administrator enabled for {user.email}. You can now sign in at /admin/login.")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
