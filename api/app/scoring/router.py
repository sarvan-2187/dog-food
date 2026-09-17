"""Score submission, normalised results, and CSV exports (PLAN.md Phase 2)."""
import csv
import io
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, require_role
from ..db import get_session
from ..events.models import Event
from ..judging.models import JudgeAssignment, Rubric
from ..submissions.models import Submission
from ..teams.models import Team
from ..timeutil import utcnow
from .models import Score
from .normalization import normalized_table
from .schemas import ResultRow, ScorePublic, ScoreWrite

router = APIRouter(tags=["scoring"])

ORGANIZER = (Role.organizer, Role.admin)


def _weighted_total(criteria: list[dict], values: dict[str, float]) -> float:
    """Raw total = sum(weight * value). Callers validate completeness first."""
    return round(sum(float(c["weight"]) * float(values[c["key"]]) for c in criteria), 6)


def _rubric_for_event(session: Session, event_id: int) -> Rubric:
    rubric = session.exec(select(Rubric).where(Rubric.event_id == event_id)).first()
    if not rubric:
        raise HTTPException(status.HTTP_409_CONFLICT, "This event has no rubric, so it cannot be scored yet.")
    return rubric


# --------------------------------------------------------------------------
# Scoring -- only the judge who owns the assignment
# --------------------------------------------------------------------------

@router.put("/api/assignments/{assignment_id}/score", response_model=ScorePublic)
def submit_score(
    assignment_id: int,
    payload: ScoreWrite,
    user: User = Depends(require_role(Role.judge)),
    session: Session = Depends(get_session),
) -> ScorePublic:
    """Restricted to the assigned judge for this specific assignment.

    require_role(judge) already excludes organizers and participants; the
    ownership check below is what stops one judge scoring another's assignment.
    """
    assignment = session.get(JudgeAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    if assignment.judge_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This submission is assigned to a different judge.")

    rubric = _rubric_for_event(session, assignment.event_id)
    criteria = rubric.criteria
    expected = {c["key"] for c in criteria}
    given = set(payload.values)
    if missing := expected - given:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Score every criterion before submitting - still missing: {', '.join(sorted(missing))}.",
        )
    if unknown := given - expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"This rubric has no criterion called: {', '.join(sorted(unknown))}.",
        )
    for criterion in criteria:
        value = payload.values[criterion["key"]]
        if not (0 <= value <= float(criterion["max_score"])):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{criterion['label']} must be between 0 and {criterion['max_score']:g}.",
            )

    score = session.exec(select(Score).where(Score.assignment_id == assignment_id)).first()
    if not score:
        score = Score(
            assignment_id=assignment_id,
            submission_id=assignment.submission_id,
            judge_id=user.id,
        )
    score.values = dict(payload.values)
    score.comment = payload.comment
    score.raw_total = _weighted_total(criteria, payload.values)
    score.updated_at = utcnow()
    session.add(score)
    record(
        session,
        "score.submitted",
        actor=user,
        entity_type="submission",
        entity_id=assignment.submission_id,
        assignment_id=assignment_id,
        raw_total=score.raw_total,
    )
    session.commit()
    session.refresh(score)
    return ScorePublic(**score.model_dump())


@router.get("/api/assignments/{assignment_id}/score", response_model=ScorePublic)
def get_my_score(
    assignment_id: int,
    user: User = Depends(require_role(Role.judge)),
    session: Session = Depends(get_session),
) -> ScorePublic:
    """A judge may re-read their own score, never another judge's."""
    assignment = session.get(JudgeAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    if assignment.judge_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This submission is assigned to a different judge.")
    score = session.exec(select(Score).where(Score.assignment_id == assignment_id)).first()
    if not score:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have not scored this submission yet.")
    return ScorePublic(**score.model_dump())


# --------------------------------------------------------------------------
# Results -- organizer/admin only
# --------------------------------------------------------------------------

def _raw_by_judge(session: Session, event_id: int) -> dict[int, dict[int, float]]:
    assignment_ids = [a.id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event_id))]
    if not assignment_ids:
        return {}
    raw: dict[int, dict[int, float]] = {}
    for score in session.exec(select(Score).where(Score.assignment_id.in_(assignment_ids))):
        raw.setdefault(score.judge_id, {})[score.submission_id] = score.raw_total
    return raw


def _result_rows(session: Session, event_id: int) -> list[ResultRow]:
    """Shared by the JSON and CSV endpoints so the two can never disagree."""
    rows = normalized_table(_raw_by_judge(session, event_id))
    out: list[ResultRow] = []
    for row in rows:
        submission = session.get(Submission, int(row["submission_id"]))
        team = session.get(Team, submission.team_id) if submission else None
        out.append(
            ResultRow(
                rank=int(row["rank"]),
                submission_id=int(row["submission_id"]),
                submission_title=(submission.title if submission else "") or "Untitled submission",
                team_name=team.name if team else "",
                judges=int(row["judges"]),
                raw_mean=float(row["raw_mean"]),
                z_bar=float(row["z_bar"]),
                display=float(row["display"]),
            )
        )
    return out


@router.get("/api/events/{event_id}/results", response_model=list[ResultRow])
def results(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> list[ResultRow]:
    """Normalised standings. Organizer/admin only -- participants and judges get
    403 here, not a filtered view."""
    return _result_rows(session, event_id)


# --------------------------------------------------------------------------
# CSV exports -- organizer/admin only, Python csv stdlib only (PLAN.md section 5)
# --------------------------------------------------------------------------

def _csv_response(filename: str, header: list[str], rows: Iterable[list]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/events/{event_id}/export/users.csv")
def export_users(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Response:
    users = session.exec(select(User).order_by(User.id)).all()
    return _csv_response(
        f"event-{event_id}-users.csv",
        ["id", "email", "name", "role", "created_at"],
        [[u.id, u.email, u.name, u.role.value, u.created_at.isoformat()] for u in users],
    )


@router.get("/api/events/{event_id}/export/submissions.csv")
def export_submissions(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Response:
    subs = session.exec(select(Submission).where(Submission.event_id == event_id).order_by(Submission.id)).all()
    rows = []
    for s in subs:
        team = session.get(Team, s.team_id)
        rows.append([s.id, s.title, team.name if team else "", s.track, s.status.value, s.updated_at.isoformat()])
    return _csv_response(
        f"event-{event_id}-submissions.csv",
        ["submission_id", "title", "team", "track", "status", "updated_at"],
        rows,
    )


@router.get("/api/events/{event_id}/export/assignments.csv")
def export_assignments(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Response:
    assignments = session.exec(
        select(JudgeAssignment).where(JudgeAssignment.event_id == event_id).order_by(JudgeAssignment.id)
    ).all()
    scored = {s.assignment_id for s in session.exec(select(Score))}
    rows = []
    for a in assignments:
        judge = session.get(User, a.judge_id)
        submission = session.get(Submission, a.submission_id)
        rows.append([
            a.id,
            a.submission_id,
            submission.title if submission else "",
            a.judge_id,
            judge.name if judge else "",
            "yes" if a.id in scored else "no",
        ])
    return _csv_response(
        f"event-{event_id}-assignments.csv",
        ["assignment_id", "submission_id", "submission_title", "judge_id", "judge_name", "scored"],
        rows,
    )


@router.get("/api/events/{event_id}/export/scores.csv")
def export_scores(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Response:
    """Raw per-judge scores. Organizer-only: this is exactly the cross-judge
    detail a judge must not see."""
    rubric = session.exec(select(Rubric).where(Rubric.event_id == event_id)).first()
    keys = [c["key"] for c in rubric.criteria] if rubric else []
    assignments = {
        a.id: a for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event_id))
    }
    rows = []
    for score in session.exec(select(Score).order_by(Score.id)):
        if score.assignment_id not in assignments:
            continue
        judge = session.get(User, score.judge_id)
        submission = session.get(Submission, score.submission_id)
        rows.append(
            [score.id, score.submission_id, submission.title if submission else "", score.judge_id,
             judge.name if judge else ""]
            + [score.values.get(k, "") for k in keys]
            + [score.raw_total, score.comment]
        )
    return _csv_response(
        f"event-{event_id}-scores.csv",
        ["score_id", "submission_id", "submission_title", "judge_id", "judge_name"] + keys + ["raw_total", "comment"],
        rows,
    )


@router.get("/api/events/{event_id}/export/results.csv")
def export_results(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Response:
    """Normalised standings, raw mean alongside the normalised value so the
    difference between the two rankings is visible (PLAN.md Phase 4 bonus)."""
    rows = _result_rows(session, event_id)
    return _csv_response(
        f"event-{event_id}-results.csv",
        ["rank", "submission_id", "submission_title", "team", "judges", "raw_mean", "z_bar", "display"],
        [[r.rank, r.submission_id, r.submission_title, r.team_name, r.judges, r.raw_mean, r.z_bar, r.display]
         for r in rows],
    )
