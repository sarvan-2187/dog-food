"""Break-glass reset link for any account, admins included (PLAN.md Phase 9.6).

    docker compose exec api python -m app.auth.reset_link someone@example.com

Shell access to the host is already total trust, so this adds no new attack
surface. It covers the one case nothing else does: an admin locked out while
email is off, with no one above them to issue a link.
"""
from __future__ import annotations

import sys

from sqlmodel import Session, select

from ..db import engine
from .models import ResetChannel, User, find_user_by_email
from .recovery import HANDOVER_TTL, issue_reset, reset_url


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: python -m app.auth.reset_link <email>", file=sys.stderr)
        return 2
    email = argv[0].strip()
    with Session(engine) as session:
        user = find_user_by_email(session, email)
        if user is None:
            print(f"No HackFlow account uses {email}.", file=sys.stderr)
            return 1
        token, _row = issue_reset(session, user, ResetChannel.cli)
        session.commit()
        minutes = int(HANDOVER_TTL.total_seconds() // 60)
        print(f"Reset link for {user.name} ({user.role.value}), valid once for {minutes} minutes:")
        print(reset_url(token))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
