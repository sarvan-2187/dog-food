"""The judge-assignment algorithm (PLAN.md section 8).

Deliberately a greedy degree-constrained assignment, not a max-flow solver:
deterministic, and testable without a database. PLAN.md is explicit that this
must not be "improved" into something non-deterministic or harder to test.

Kept free of session/ORM access so it can be exercised on plain objects.
"""
from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from .models import JudgeAssignment

DEFAULT_JUDGES_PER_SUBMISSION = 3


class _HasTeam(Protocol):
    id: int
    team_id: int
    event_id: int


class _HasId(Protocol):
    id: int


class _Membership(Protocol):
    team_id: int
    user_id: int


def build_conflict_set(
    submissions: Iterable[_HasTeam],
    team_memberships: Iterable[_Membership],
) -> set[tuple[int, int]]:
    """Step 1: (judge_id, submission_id) pairs where the judge is on the
    submitting team. A judge must never score their own team's work."""
    members_by_team: dict[int, set[int]] = {}
    for membership in team_memberships:
        members_by_team.setdefault(membership.team_id, set()).add(membership.user_id)

    conflicts: set[tuple[int, int]] = set()
    for submission in submissions:
        for user_id in members_by_team.get(submission.team_id, ()):
            conflicts.add((user_id, submission.id))
    return conflicts


def assign_judges(
    submissions: Sequence[_HasTeam],
    judges: Sequence[_HasId],
    team_memberships: Sequence[_Membership],
    k: int = DEFAULT_JUDGES_PER_SUBMISSION,
) -> list[JudgeAssignment]:
    """Assign up to `k` non-conflicted judges to each submission.

    Step 2: iterate submissions round-robin; for each, take the `k` eligible
    judges with the fewest assignments so far, breaking ties by judge id
    ascending so the result is reproducible.

    Fewer than `k` judges are assigned when conflicts leave too few eligible --
    that is reported honestly rather than papered over by relaxing a conflict.
    """
    if k <= 0:
        return []

    conflicts = build_conflict_set(submissions, team_memberships)
    load: dict[int, int] = {judge.id: 0 for judge in judges}
    judge_ids = sorted(load)

    assignments: list[JudgeAssignment] = []
    for submission in sorted(submissions, key=lambda s: s.id):
        eligible = [j for j in judge_ids if (j, submission.id) not in conflicts]
        # Fewest assignments first, then judge id -- both keys are total, so the
        # ordering is fully determined and the run is reproducible.
        eligible.sort(key=lambda j: (load[j], j))
        for judge_id in eligible[:k]:
            assignments.append(
                JudgeAssignment(
                    event_id=submission.event_id,
                    submission_id=submission.id,
                    judge_id=judge_id,
                )
            )
            load[judge_id] += 1
    return assignments


def coverage_report(
    submissions: Sequence[_HasTeam],
    assignments: Sequence[JudgeAssignment],
    k: int = DEFAULT_JUDGES_PER_SUBMISSION,
) -> dict[int, int]:
    """submission_id -> how many judges short of `k` it ended up. Non-zero
    entries are what the organizer needs told about, not hidden."""
    counts = {s.id: 0 for s in submissions}
    for assignment in assignments:
        if assignment.submission_id in counts:
            counts[assignment.submission_id] += 1
    return {sid: k - n for sid, n in counts.items() if n < k}
