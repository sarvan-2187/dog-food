"""Score submission, normalised results, and CSV exports (PLAN.md Phase 2)."""
import csv
import io
import secrets
from datetime import datetime
from typing import Iterable, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user, mailer, require_role
from ..db import get_session
from ..events.models import Event
from ..events.questions import new_question_id
from ..events.schemas import stages_to_json
from ..events.visibility import may_see_results, results_are_public
from ..judging.event_judges import assert_in_track, assignment_outside_track
from ..auth.security import hash_password
from ..judging.models import EventJudge, JudgeAssignment, Rubric
from ..submissions.models import Submission, SubmissionStatus, in_competition
from ..teams.models import Team, TeamMembership
from ..timeutil import ensure_utc, utcnow
from ..webhooks.service import notify
from .awards import awards_by_submission
from .certificate import TEMPLATES, certificate_serial, render_certificate, submission_for_serial
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


def _existing_event(session: Session, event_id: int) -> Event:
    """Results and exports for an event id that doesn't exist are a 404, not an
    empty 200 that reads as "nobody has been scored yet"."""
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


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
    assert_in_track(session, assignment)
    event = session.get(Event, assignment.event_id)
    if event is not None and utcnow() < event.end_at:
        # PLAN.md 10.3: covers assignments made before judging was gated on the deadline.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Judging opens when submissions close on {event.end_at.strftime('%d %b %Y at %H:%M UTC')} - "
            "until then the team can still change what you'd be scoring.",
        )

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
        late=_is_late(session, assignment.event_id),
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
    assert_in_track(session, assignment)
    score = session.exec(select(Score).where(Score.assignment_id == assignment_id)).first()
    if not score:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have not scored this submission yet.")
    return ScorePublic(**score.model_dump())


@router.get("/api/judges/{judge_ref}/scores", response_model=list[ScorePublic])
def judge_scores(
    judge_ref: str,
    user: User = Depends(require_role(Role.judge, *ORGANIZER)),
    session: Session = Depends(get_session),
) -> list[ScorePublic]:
    """Every score one judge has given. `judge_ref` is "me" or a user id. A judge
    may read only their own; asking for a peer's is refused and audited, so an
    organizer can see who went looking. Organizers may read any judge's."""
    if judge_ref == "me":
        judge_id = user.id
    elif judge_ref.isdigit():
        judge_id = int(judge_ref)
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Judge not found.")
    if user.role == Role.judge and judge_id != user.id:
        record(session, "score.peer_read_refused", actor=user, entity_type="user", entity_id=judge_id)
        session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Judges can only read their own scores.")
    scores = list(session.exec(select(Score).where(Score.judge_id == judge_id).order_by(Score.id)))
    if user.role == Role.judge:
        # A track judge never sees an entry outside their track, even their own
        # score from before the track was set (DOGFOOD T2).
        scores = [
            s for s in scores
            if (a := session.get(JudgeAssignment, s.assignment_id)) is None or not assignment_outside_track(session, a)
        ]
    return [ScorePublic(**s.model_dump()) for s in scores]


def _is_late(session: Session, event_id: int) -> bool:
    """Past the event's soft judging deadline. Recorded, never enforced."""
    event = session.get(Event, event_id)
    return bool(event and event.judging_deadline and utcnow() > event.judging_deadline)


# --------------------------------------------------------------------------
# Results -- organizer/admin only
# --------------------------------------------------------------------------

def _raw_by_judge(session: Session, event_id: int) -> dict[int, dict[int, float]]:
    assignment_ids = [a.id for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event_id))]
    if not assignment_ids:
        return {}
    raw: dict[int, dict[int, float]] = {}
    # A disqualified entry's scores are kept (reinstating restores them) but left out
    # here, so every judge's normalization is recomputed as if it were never judged.
    competing = select(Submission.id).where(Submission.event_id == event_id, in_competition())
    for score in session.exec(
        select(Score).where(Score.assignment_id.in_(assignment_ids), Score.submission_id.in_(competing))
    ):
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
    _existing_event(session, event_id)
    return _result_rows(session, event_id)


# --------------------------------------------------------------------------
# CSV exports -- organizer/admin only, Python csv stdlib only (PLAN.md section 5)
# --------------------------------------------------------------------------

# A cell starting with one of these is run as a formula when the CSV is opened
# in Excel, LibreOffice or Google Sheets. Titles, team names, answers, comments
# and user names are typed by participants, so "=HYPERLINK(...)" in a project
# title would otherwise execute on the organizer's machine (CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value):
    """OWASP's advice: prefix such a text cell with a single quote so it is read
    as text. Numbers are left alone, so a negative score stays a number."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _csv_response(filename: str, header: list[str], rows: Iterable[list]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([_csv_safe(h) for h in header])
    writer.writerows([_csv_safe(v) for v in row] for row in rows)
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
    _existing_event(session, event_id)
    # The people of THIS event: its team members and its judges. It used to
    # list every account on the platform, so any organizer could download the
    # names and emails of people in other organizers' events.
    team_ids = select(Team.id).where(Team.event_id == event_id)
    member_ids = select(TeamMembership.user_id).where(TeamMembership.team_id.in_(team_ids))
    panel_ids = select(EventJudge.user_id).where(EventJudge.event_id == event_id)
    assigned_ids = select(JudgeAssignment.judge_id).where(JudgeAssignment.event_id == event_id)
    users = session.exec(
        select(User)
        .where(User.id.in_(member_ids) | User.id.in_(panel_ids) | User.id.in_(assigned_ids))
        .order_by(User.id)
    ).all()
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
    _existing_event(session, event_id)
    subs = session.exec(select(Submission).where(Submission.event_id == event_id).order_by(Submission.id)).all()
    event = session.get(Event, event_id)
    # One column per custom question, hidden ones included: an answer given is
    # part of the record even after the organizer retires the question.
    questions = (event.questions or []) if event else []
    rows = []
    for s in subs:
        team = session.get(Team, s.team_id)
        answers = s.answers or {}
        rows.append([
            s.id, s.title, s.tagline, team.name if team else "", s.track, "; ".join(s.tech_tags or []),
            s.status.value, s.repo_url, s.demo_url, s.video_url, s.updated_at.isoformat(),
        ] + [answers.get(q["id"], "") for q in questions])
    return _csv_response(
        f"event-{event_id}-submissions.csv",
        ["submission_id", "title", "tagline", "team", "track", "tech_tags", "status", "repo_url", "demo_url",
         "video_url", "updated_at"] + [f"Q: {q['prompt']}" for q in questions],
        rows,
    )


@router.get("/api/events/{event_id}/export/assignments.csv")
def export_assignments(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Response:
    _existing_event(session, event_id)
    assignments = session.exec(
        select(JudgeAssignment).where(JudgeAssignment.event_id == event_id).order_by(JudgeAssignment.id)
    ).all()
    scored = {
        s.assignment_id
        for s in session.exec(select(Score).where(Score.assignment_id.in_([a.id for a in assignments] or [0])))
    }
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
    _existing_event(session, event_id)
    keys = [c["key"] for c in _combined_criteria(_rubrics_for_event_or_empty(session, event_id))]
    assignments = {
        a.id: a for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event_id))
    }
    rows = []
    for score in session.exec(
        select(Score).where(Score.assignment_id.in_(list(assignments) or [0])).order_by(Score.id)
    ):
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
    _existing_event(session, event_id)
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
    record_ = _certificate_record(session, submission, event)
    pdf_bytes = render_certificate(
        event_name=event.name,
        team_name=record_.team_name,
        submission_title=record_.submission_title,
        rank=record_.rank,
        prizes=record_.prizes,
        members=record_.members,
        event_dates=record_.event_dates,
        issued_on=(event.results_hidden_until or utcnow()).date(),
        serial=record_.serial,
        verify_url=f"{mailer.APP_BASE_URL}/verify/{record_.serial}",
        template=event.certificate_template,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="submission-{submission_id}-certificate.pdf"'},
    )


# --------------------------------------------------------------------------
# Bulk event export/import (PLAN.md Phase 4 T4; DOGFOOD T4: "leave as easily
# as they arrived"). The backup carries the event's config, rubrics, teams with
# their members, submissions, judge panel, assignments and scores, so a whole
# event moves between installs. People are matched by email:
#
# - a team member with an account here is linked to it, its password and role
#   untouched; one without gets a new participant account with a random
#   password nobody knows, and the organizer sends them a reset link;
# - a judge must already hold the judge role here. The role is only ever
#   granted by invitation, so import never creates or promotes a judge.
#
# All or nothing: every judge and rubric criterion a score, assignment or panel
# row refers to must match, or the import is refused with a 422 that lists
# what didn't, and nothing is written. Scores are never imported partially.
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
    teams = session.exec(select(Team).where(Team.event_id == event_id).order_by(Team.id)).all()
    submissions = session.exec(select(Submission).where(Submission.event_id == event_id).order_by(Submission.id)).all()
    team_names = {t.id: t.name for t in teams}
    team_of_submission = {s.id: team_names.get(s.team_id, "") for s in submissions}
    users: dict[int, User] = {}

    def person(user_id: "int | None") -> "User | None":
        if user_id is not None and user_id not in users:
            users[user_id] = session.get(User, user_id)
        return users.get(user_id) if user_id is not None else None

    members_by_team: dict[int, list[TeamMembership]] = {}
    for m in session.exec(
        select(TeamMembership).where(TeamMembership.team_id.in_(list(team_names) or [0])).order_by(TeamMembership.id)
    ):
        members_by_team.setdefault(m.team_id, []).append(m)
    panel = session.exec(select(EventJudge).where(EventJudge.event_id == event_id).order_by(EventJudge.id)).all()
    assignments = session.exec(
        select(JudgeAssignment).where(JudgeAssignment.event_id == event_id).order_by(JudgeAssignment.id)
    ).all()
    scores = (
        session.exec(select(Score).where(Score.assignment_id.in_([a.id for a in assignments])).order_by(Score.id)).all()
        if assignments
        else []
    )
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
            "voting_access": event.voting_access,
            "results_hidden_until": event.results_hidden_until.isoformat() if event.results_hidden_until else None,
            "rules": event.rules,
            "stages": event.stages,
            "certificate_template": event.certificate_template,
            "questions": event.questions or [],
        },
        "rubrics": [{"name": r.name, "criteria": r.criteria} for r in rubrics],
        "teams": [
            {
                "name": t.name,
                "members": [
                    {"email": u.email, "name": u.name}
                    for m in members_by_team.get(t.id, [])
                    if (u := person(m.user_id)) is not None
                ],
                "captain_email": captain.email if (captain := person(t.captain_id)) else None,
            }
            for t in teams
        ],
        "submissions": [
            {
                "team_name": team_names.get(s.team_id, ""),
                "title": s.title,
                "tagline": s.tagline,
                "description": s.description,
                "track": s.track,
                "tech_tags": s.tech_tags or [],
                "answers": s.answers or {},
                "status": s.status.value,
                "repo_url": s.repo_url,
                "demo_url": s.demo_url,
                "video_url": s.video_url,
            }
            for s in submissions
        ],
        "judges": [
            {"email": u.email, "name": u.name, "track": j.track}
            for j in panel
            if (u := person(j.user_id)) is not None
        ],
        "assignments": [
            {"team_name": team_of_submission.get(a.submission_id, ""), "judge_email": u.email}
            for a in assignments
            if (u := person(a.judge_id)) is not None
        ],
        "scores": [
            {
                "team_name": team_of_submission.get(sc.submission_id, ""),
                "judge_email": u.email,
                "values": sc.values,
                "comment": sc.comment,
            }
            for sc in scores
            if (u := person(sc.judge_id)) is not None
        ],
    }


def _imported_questions(payload: EventImportPayload) -> list[dict]:
    """A backup's questions keep their ids, so its answers still line up. A
    question with no id, or a repeated one, gets a fresh id."""
    out: list[dict] = []
    for q in payload.questions:
        qid = q.id if q.id and q.id not in {o["id"] for o in out} else new_question_id()
        out.append({"id": qid, "prompt": q.prompt, "required": q.required, "hidden": q.hidden, "public": q.public})
    return out


def _account(session: Session, email: str) -> "User | None":
    return session.exec(select(User).where(func.lower(User.email) == email.strip().lower())).first()


def _check_people(session: Session, payload: EventImportPayload) -> tuple[dict[str, User], list[str]]:
    """Everything the people half of an import refers to, checked before a row
    is written: (judge accounts by lowercased email, problems). Any problem
    refuses the whole import."""
    problems: list[str] = []
    criteria: dict[str, dict] = {}
    for r in payload.rubrics:
        for c in r.criteria:
            well_formed = isinstance(c, dict) and {"key", "weight", "max_score"} <= set(c)
            if well_formed and all(isinstance(c[k], (int, float)) for k in ("weight", "max_score")):
                criteria[c["key"]] = c
            elif payload.scores:
                problems.append(f"Rubric {r.name!r} has a criterion without a key, weight and max_score.")
    submitted_teams = {s.team_name for s in payload.submissions}
    tracks = set(payload.tracks)

    seen_members: dict[str, str] = {}
    for t in payload.teams:
        for m in t.members:
            email = m.email.strip().lower()
            if "@" not in email:
                problems.append(f"Team {t.name!r} has a member with no valid email ({m.email!r}).")
            elif email in seen_members:
                problems.append(f"{m.email} is on two teams ({seen_members[email]!r} and {t.name!r}).")
            else:
                seen_members[email] = t.name

    judges: dict[str, User] = {}
    for j in payload.judges:
        email = j.email.strip().lower()
        account = _account(session, email)
        if account is None or account.role != Role.judge:
            problems.append(f"Judge {j.email} has no judge account here. Invite them as a judge first.")
        else:
            judges[email] = account
        if j.track and j.track not in tracks:
            problems.append(f"Judge {j.email} is on track {j.track!r}, which this event doesn't have.")

    def check_ref(kind: str, team_name: str, judge_email: str) -> None:
        if team_name not in submitted_teams:
            problems.append(f"A {kind} refers to team {team_name!r}, which has no submission in this backup.")
        if judge_email.strip().lower() not in judges:
            problems.append(f"A {kind} for {team_name!r} refers to judge {judge_email}, who isn't a matched judge.")

    for a in payload.assignments:
        check_ref("judge assignment", a.team_name, a.judge_email)
    for sc in payload.scores:
        check_ref("score", sc.team_name, sc.judge_email)
        if set(sc.values) != set(criteria):
            missing, extra = set(criteria) - set(sc.values), set(sc.values) - set(criteria)
            detail = "; ".join(
                part
                for part in (
                    f"missing {', '.join(sorted(missing))}" if missing else "",
                    f"no rubric criterion called {', '.join(sorted(extra))}" if extra else "",
                )
                if part
            )
            problems.append(f"{sc.judge_email}'s score for {sc.team_name!r} doesn't match the rubrics: {detail}.")
            continue
        for key, value in sc.values.items():
            if not (0 <= value <= float(criteria[key]["max_score"])):
                problems.append(
                    f"{sc.judge_email}'s score for {sc.team_name!r} gives {key} {value:g}, "
                    f"outside 0 to {criteria[key]['max_score']:g}."
                )
    # A backup lists each thing once; repeats would violate the unique keys below.
    pairs = [(sc.team_name, sc.judge_email.strip().lower()) for sc in payload.scores]
    if len(set(pairs)) != len(pairs):
        problems.append("The backup has two scores from the same judge for the same team.")
    return judges, problems


@router.post("/api/events/import", response_model=Event, status_code=status.HTTP_201_CREATED)
def import_event(
    payload: EventImportPayload,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> Event:
    if session.exec(select(Event).where(Event.slug == payload.slug)).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "An event with this slug already exists.")
    judges, problems = _check_people(session, payload)
    if problems:
        shown = problems[:10]
        more = f" (and {len(problems) - 10} more)" if len(problems) > 10 else ""
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Nothing was imported. Fix these and try again: " + " ".join(shown) + more,
        )

    event = Event(
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        start_at=ensure_utc(datetime.fromisoformat(payload.start_at)),
        end_at=ensure_utc(datetime.fromisoformat(payload.end_at)),
        tracks=payload.tracks,
        prize_config=payload.prize_config,
        voting_enabled=payload.voting_enabled,
        voting_access=payload.voting_access,
        results_hidden_until=ensure_utc(datetime.fromisoformat(payload.results_hidden_until))
        if payload.results_hidden_until
        else None,
        created_by_id=user.id,
        rules=payload.rules,
        stages=stages_to_json(payload.stages),
        certificate_template=payload.certificate_template if payload.certificate_template in TEMPLATES else "classic",
        status="draft",  # PLAN.md 10.12: an import is reviewed before it goes public
        questions=_imported_questions(payload),
    )
    session.add(event)
    session.flush()

    for r in payload.rubrics:
        session.add(Rubric(event_id=event.id, name=r.name, criteria=r.criteria))
    criteria = [c for r in payload.rubrics for c in r.criteria]

    created_accounts = 0
    team_ids_by_name: dict[str, int] = {}
    for t in payload.teams:
        team = Team(event_id=event.id, name=t.name)
        session.add(team)
        session.flush()
        team_ids_by_name[t.name] = team.id
        member_ids: dict[str, int] = {}
        for m in t.members:
            account = _account(session, m.email)
            if account is None:
                # Nobody knows this password: the organizer sends a reset link.
                account = User(
                    email=m.email.strip(),
                    name=m.name.strip() or m.email.split("@")[0],
                    role=Role.participant,
                    password_hash=hash_password(secrets.token_urlsafe(32)),
                )
                session.add(account)
                session.flush()
                created_accounts += 1
                record(
                    session, "user.created_by_import", actor=user, entity_type="user", entity_id=account.id,
                    event_id=event.id,
                )
            session.add(TeamMembership(team_id=team.id, user_id=account.id))
            member_ids[m.email.strip().lower()] = account.id
        captain = (t.captain_email or "").strip().lower()
        team.captain_id = member_ids.get(captain) or next(iter(member_ids.values()), None)
        session.add(team)

    question_ids = {q["id"] for q in event.questions}
    submission_ids: dict[str, int] = {}
    for s in payload.submissions:
        team_id = team_ids_by_name.get(s.team_name)
        if team_id is None:
            continue
        submission = Submission(
            team_id=team_id,
            event_id=event.id,
            title=s.title,
            tagline=s.tagline,
            description=s.description,
            track=s.track,
            tech_tags=s.tech_tags,
            # Only answers to a question this event actually has.
            answers={k: v for k, v in s.answers.items() if k in question_ids},
            repo_url=s.repo_url,
            demo_url=s.demo_url,
            video_url=s.video_url,
            status=SubmissionStatus(s.status),
        )
        session.add(submission)
        session.flush()
        submission_ids[s.team_name] = submission.id

    for j in payload.judges:
        account = judges[j.email.strip().lower()]
        session.add(EventJudge(event_id=event.id, user_id=account.id, added_by_id=user.id, track=j.track or None))

    assignment_ids: dict[tuple[int, int], int] = {}

    def assignment_for(team_name: str, judge_email: str) -> tuple[int, int, int]:
        sub_id, judge_id = submission_ids[team_name], judges[judge_email.strip().lower()].id
        if (sub_id, judge_id) not in assignment_ids:
            row = JudgeAssignment(event_id=event.id, submission_id=sub_id, judge_id=judge_id)
            session.add(row)
            session.flush()
            assignment_ids[(sub_id, judge_id)] = row.id
        return assignment_ids[(sub_id, judge_id)], sub_id, judge_id

    for a in payload.assignments:
        assignment_for(a.team_name, a.judge_email)
    for sc in payload.scores:
        # A score implies its assignment, so a backup missing one still lines up.
        assignment_id, sub_id, judge_id = assignment_for(sc.team_name, sc.judge_email)
        session.add(
            Score(
                assignment_id=assignment_id,
                submission_id=sub_id,
                judge_id=judge_id,
                values=dict(sc.values),
                comment=sc.comment[:2000],
                raw_total=_weighted_total(criteria, sc.values),
            )
        )

    record(
        session, "event.imported", actor=user, entity_type="event", entity_id=event.id, slug=event.slug,
        teams=len(payload.teams), created_accounts=created_accounts, judges=len(payload.judges),
        assignments=len(assignment_ids), scores=len(payload.scores),
    )
    session.commit()
    session.refresh(event)
    return event


class CertificateRecord(BaseModel):
    """What a certificate says. The public /verify page shows exactly this."""

    serial: str
    event_name: str
    event_slug: str
    event_dates: str
    team_name: str
    members: list[str]
    submission_title: str
    rank: Optional[int] = None
    prizes: list[str] = []


def _event_dates(event: Event) -> str:
    start, end = ensure_utc(event.start_at), ensure_utc(event.end_at)
    if start.date() == end.date():
        return start.strftime("%d %B %Y")
    return f"{start.strftime('%d %B')} - {end.strftime('%d %B %Y')}"


def _certificate_record(session: Session, submission: Submission, event: Event) -> CertificateRecord:
    team = session.get(Team, submission.team_id)
    member_ids = [
        m.user_id for m in session.exec(select(TeamMembership).where(TeamMembership.team_id == submission.team_id))
    ]
    members = sorted(u.name for u in session.exec(select(User).where(User.id.in_(member_ids or [0]))))
    rank = next((r.rank for r in _result_rows(session, event.id) if r.submission_id == submission.id), None)
    return CertificateRecord(
        serial=certificate_serial(submission.id),
        event_name=event.name,
        event_slug=event.slug,
        event_dates=_event_dates(event),
        team_name=team.name if team else "",
        members=members,
        submission_title=submission.title or "Untitled submission",
        rank=rank,
        prizes=awards_by_submission(session, [submission.id]).get(submission.id, []),
    )


@router.get("/api/certificates/{serial}", response_model=CertificateRecord)
def verify_certificate(serial: str, session: Session = Depends(get_session)) -> CertificateRecord:
    """Public, no sign-in: confirm a certificate is genuine and see what it
    certifies. A forged, mistyped or not-yet-public serial all read the same,
    so this can't be used to probe which submissions exist."""
    not_found = HTTPException(status.HTTP_404_NOT_FOUND, "No certificate matches that code.")
    submission_id = submission_for_serial(serial)
    submission = session.get(Submission, submission_id) if submission_id else None
    if submission is None or not submission.competing:
        raise not_found
    event = session.get(Event, submission.event_id)
    if event is None or event.status != "published" or not results_are_public(event):
        raise not_found
    return _certificate_record(session, submission, event)
