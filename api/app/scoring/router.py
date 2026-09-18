"""Score submission, normalised results, and CSV exports (PLAN.md Phase 2)."""
import csv
import io
from datetime import datetime
from typing import Iterable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, require_role
from ..db import get_session
from ..events.models import Event
from ..events.visibility import may_see_results
from ..judging.models import JudgeAssignment, Rubric
from ..submissions.models import Submission, SubmissionStatus
from ..teams.models import Team, TeamMembership
from ..timeutil import ensure_utc, utcnow
from ..webhooks.service import notify
from .certificate import render_certificate
from .models import Score
from .normalization import normalized_table
from .schemas import EventImportPayload, ResultRow, ScorePublic, ScoreWrite

router = APIRouter(tags=["scoring"])

ORGANIZER = (Role.organizer, Role.admin)


def _weighted_total(criteria: list[dict], values: dict[str, float]) -> float:
    """Raw total = sum(weight * value). Callers validate completeness first."""
    return round(sum(float(c["weight"]) * float(values[c["key"]]) for c in criteria), 6)


def _rubrics_for_event_or_empty(session: Session, event_id: int) -> list[Rubric]:
    return list(session.exec(select(Rubric).where(Rubric.event_id == event_id).order_by(Rubric.id)))


def _rubrics_for_event(session: Session, event_id: int) -> list[Rubric]:
    rubrics = _rubrics_for_event_or_empty(session, event_id)
    if not rubrics:
        raise HTTPException(status.HTTP_409_CONFLICT, "This event has no rubric, so it cannot be scored yet.")
    return rubrics


def _combined_criteria(rubrics: list[Rubric]) -> list[dict]:
    """The flat criteria list every submission is actually scored against --
    every rubric in the event's set, concatenated (PLAN.md Open Questions)."""
    return [c for r in rubrics for c in r.criteria]


# --------------------------------------------------------------------------
# Scoring -- only the judge who owns the assignment
# --------------------------------------------------------------------------

@router.put("/api/assignments/{assignment_id}/score", response_model=ScorePublic)
def submit_score(
    assignment_id: int,
    payload: ScoreWrite,
    background_tasks: BackgroundTasks,
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

    criteria = _combined_criteria(_rubrics_for_event(session, assignment.event_id))
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
    notify(session, background_tasks, assignment.event_id, "score.submitted", submission_id=assignment.submission_id)
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
    keys = [c["key"] for c in _combined_criteria(_rubrics_for_event_or_empty(session, event_id))]
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


# --------------------------------------------------------------------------
# Certificates (PLAN.md Phase 4 T4) -- one per submission, once results are
# visible. Same visibility gate as public results: an organizer/admin may
# always fetch one; anyone else must wait for results_hidden_until, and must
# actually be on the submitting team.
# --------------------------------------------------------------------------

@router.get("/api/submissions/{submission_id}/certificate.pdf")
def certificate(
    submission_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    submission = session.get(Submission, submission_id)
    if not submission:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found.")
    event = session.get(Event, submission.event_id)
    on_team = session.exec(
        select(TeamMembership).where(TeamMembership.team_id == submission.team_id, TeamMembership.user_id == user.id)
    ).first()
    if not on_team and user.role not in (Role.organizer, Role.admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the submitting team may download this certificate.")
    if not may_see_results(event, user):
        raise HTTPException(
            status.HTTP_425_TOO_EARLY,
            f"Certificates are available once results are revealed on "
            f"{event.results_hidden_until.strftime('%d %b %Y at %H:%M UTC') if event.results_hidden_until else 'a date the organizer sets'}.",
        )
    team = session.get(Team, submission.team_id)
    rank = next((r.rank for r in _result_rows(session, event.id) if r.submission_id == submission_id), None)
    pdf_bytes = render_certificate(
        event_name=event.name,
        team_name=team.name if team else "",
        submission_title=submission.title or "Untitled submission",
        rank=rank,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="submission-{submission_id}-certificate.pdf"'},
    )


# --------------------------------------------------------------------------
# Bulk event export/import (PLAN.md Phase 4 T4). Scoped to what an organizer
# would actually restore or migrate -- event config, rubric, teams, and
# submissions. Judge assignments/scores are deliberately NOT round-tripped:
# they are tied to specific judge accounts, and silently re-creating scores
# against a re-assigned (necessarily different) judge would misrepresent who
# actually judged what. An organizer re-runs assignment and judging fresh on
# the imported event instead.
# --------------------------------------------------------------------------

@router.get("/api/events/{event_id}/export.json")
def export_event(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> dict:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    rubrics = _rubrics_for_event_or_empty(session, event_id)
    teams = session.exec(select(Team).where(Team.event_id == event_id)).all()
    submissions = session.exec(select(Submission).where(Submission.event_id == event_id)).all()
    team_names = {t.id: t.name for t in teams}
    return {
        "event": {
            "slug": event.slug,
            "name": event.name,
            "description": event.description,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat(),
            "tracks": event.tracks,
            "prize_config": event.prize_config,
            "voting_enabled": event.voting_enabled,
            "results_hidden_until": event.results_hidden_until.isoformat() if event.results_hidden_until else None,
        },
        "rubrics": [{"name": r.name, "criteria": r.criteria} for r in rubrics],
        "teams": [{"name": t.name} for t in teams],
        "submissions": [
            {
                "team_name": team_names.get(s.team_id, ""),
                "title": s.title,
                "description": s.description,
                "track": s.track,
                "status": s.status.value,
            }
            for s in submissions
        ],
    }


@router.post("/api/events/import", response_model=Event, status_code=status.HTTP_201_CREATED)
def import_event(
    payload: EventImportPayload,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Event:
    if session.exec(select(Event).where(Event.slug == payload.slug)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An event with this slug already exists.")
    event = Event(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        start_at=ensure_utc(datetime.fromisoformat(payload.start_at)),
        end_at=ensure_utc(datetime.fromisoformat(payload.end_at)),
        tracks=payload.tracks,
        prize_config=payload.prize_config,
        voting_enabled=payload.voting_enabled,
        results_hidden_until=ensure_utc(datetime.fromisoformat(payload.results_hidden_until))
        if payload.results_hidden_until
        else None,
        created_by_id=user.id,
    )
    session.add(event)
    session.flush()

    for r in payload.rubrics:
        session.add(Rubric(event_id=event.id, name=r.name, criteria=r.criteria))

    team_ids_by_name: dict[str, int] = {}
    for t in payload.teams:
        team = Team(event_id=event.id, name=t.name)
        session.add(team)
        session.flush()
        team_ids_by_name[t.name] = team.id

    for s in payload.submissions:
        team_id = team_ids_by_name.get(s.team_name)
        if team_id is None:
            continue
        session.add(
            Submission(
                team_id=team_id,
                event_id=event.id,
                title=s.title,
                description=s.description,
                track=s.track,
                status=SubmissionStatus(s.status),
            )
        )

    record(session, "event.imported", actor=user, entity_type="event", entity_id=event.id, slug=event.slug)
    session.commit()
    session.refresh(event)
    return event
