"""When results become public (PLAN.md Phase 3).

One predicate, imported everywhere, so the gallery, the public results endpoint
and the UI can never disagree about whether the window is open.
"""
from __future__ import annotations

from typing import Optional

from ..auth.models import Role, User
from ..timeutil import utcnow
from .models import Event


def results_are_public(event: Event) -> bool:
    """True once `results_hidden_until` has passed (or was never set)."""
    return event.results_hidden_until is None or utcnow() >= event.results_hidden_until


def may_see_results(event: Event, user: Optional[User]) -> bool:
    """Organizers and admins run the event, so they see standings during the
    hidden window -- they need them to run it. Everyone else, including judges
    and signed-out visitors, waits. See Open Questions.
    """
    if user is not None and user.role in (Role.organizer, Role.admin):
        return True
    return results_are_public(event)
