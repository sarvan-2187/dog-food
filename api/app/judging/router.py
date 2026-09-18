"""Rubric CRUD, assignment runs, and the judge progress dashboard."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from .. import crypto
from ..audit.log import record
from ..auth import Role, User, get_current_user, require_role
from ..db import get_session
from ..events.models import Event
from ..scoring.models import Score
from ..submissions.models import Submission
from ..teams.models import TeamMembership
from ..timeutil import utcnow
from ..webhooks.service import notify
from .assignment import assign_judges, coverage_report
from .models import JudgeAssignment, Rubric
from .schemas import (
    WEIGHT_SUM_TOLERANCE,
    AssignmentPublic,
    AssignmentRun,
    AssignmentSummary,
    CoverageWarning,
    JudgeProgress,
    RubricGroup,
    RubricWrite,
    ScoringSheet,
)

router = APIRouter(tags=["judging"])


def _event_or_404(session: Session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


# --------------------------------------------------------------------------
# Rubric CRUD -- organizer/admin only. An event's rubrics are a SET: several
# named rubrics, each with its own criteria, combined into one flat criteria
# list (grouped by rubric name) that every submission in the event is scored
# against. Editing/adding/removing any rubric is blocked once any judge has
# actually scored anything in the event -- changing the set after that would
# silently invalidate scores already given.
# --------------------------------------------------------------------------

def _rubrics_for_event(session: Session, event_id: int) -> list[Rubric]:
    return list(session.exec(select(Rubric).where(Rubric.event_id == event_id).order_by(Rubric.id)))


def _scoring_started(session: Session, event_id: int) -> bool:
    return session.exec(select(Score).join(JudgeAssignment).where(JudgeAssignment.event_id == event_id)).first() is not None


def _assert_keys_free(session: Session, event_id: int, criteria: list[dict], exclude_rubric_id: "int | None" = None) -> None:
    """Score.values is one flat dict keyed by criterion key across every rubric
    in the event, so two rubrics can't reuse the same key -- there'd be no way
    to tell which criterion a given value belonged to."""
    taken: set[str] = set()
    for r in _rubrics_for_event(session, event_id):
        if r.id == exclude_rubric_id:
            continue
        taken.update(c["key"] for c in r.criteria)
    collisions = taken & {c["key"] for c in criteria}
    if collisions:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"These criterion keys are already used by another rubric in this event: {', '.join(sorted(collisions))}.",
        )


@router.get("/api/events/{event_id}/rubrics", response_model=list[Rubric])
def list_rubrics(
    event_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[Rubric]:
    """Readable by any signed-in user: a judge needs the criteria to score, and a
    participant is entitled to know what they are being judged on. It carries no
    scores, so this is not score data."""
    return _rubrics_for_event(session, event_id)


@router.post("/api/events/{event_id}/rubrics", response_model=Rubric, status_code=status.HTTP_201_CREATED)
def create_rubric(
    event_id: int,
    payload: RubricWrite,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> Rubric:
    _event_or_404(session, event_id)
    if _scoring_started(session, event_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Judges have already scored in this event, so its rubric set can no longer change.",
        )
    criteria = [c.model_dump() for c in payload.criteria]
    _assert_keys_free(session, event_id, criteria)
    rubric = Rubric(event_id=event_id, name=payload.name, criteria=criteria)
    session.add(rubric)
    session.flush()
    record(session, "rubric.created", actor=user, entity_type="event", entity_id=event_id, rubric_id=rubric.id)
    session.commit()
    session.refresh(rubric)
    return rubric


@router.put("/api/events/{event_id}/rubrics/{rubric_id}", response_model=Rubric)
def update_rubric(
    event_id: int,
    rubric_id: int,
    payload: RubricWrite,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> Rubric:
    rubric = session.get(Rubric, rubric_id)
    if not rubric or rubric.event_id != event_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such rubric on this event.")
    if _scoring_started(session, event_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Judges have already scored in this event, so its rubric criteria can no longer be changed.",
        )
    criteria = [c.model_dump() for c in payload.criteria]
    _assert_keys_free(session, event_id, criteria, exclude_rubric_id=rubric.id)
    rubric.name = payload.name
    rubric.criteria = criteria
    rubric.updated_at = utcnow()
    session.add(rubric)
    record(session, "rubric.updated", actor=user, entity_type="event", entity_id=event_id, rubric_id=rubric.id)
    session.commit()
    session.refresh(rubric)
    return rubric


@router.delete("/api/events/{event_id}/rubrics/{rubric_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rubric(
    event_id: int,
    rubric_id: int,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> None:
    rubric = session.get(Rubric, rubric_id)
    if not rubric or rubric.event_id != event_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such rubric on this event.")
    if _scoring_started(session, event_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Judges have already scored in this event, so none of its rubrics can be deleted now.",
        )
    record(session, "rubric.deleted", actor=user, entity_type="event", entity_id=event_id, rubric_id=rubric_id)
    session.delete(rubric)
    session.commit()


# --------------------------------------------------------------------------
# Assignment run -- organizer/admin only
# --------------------------------------------------------------------------

@router.post("/api/events/{event_id}/assignments", response_model=AssignmentSummary, status_code=status.HTTP_201_CREATED)
def run_assignment(
    event_id: int,
    payload: AssignmentRun,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> AssignmentSummary:
    """Idempotent: re-running adds only the pairs that do not exist yet, so an
    organizer can assign again after late submissions without duplicating work."""
    _event_or_404(session, event_id)
    rubrics = _rubrics_for_event(session, event_id)
    if not rubrics:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Set this event's rubric before assigning judges - judges need criteria to score against.",
        )
    # The combined set's weights must sum to 1.0 before judging can start --
    # checked here, not on every individual rubric save, since an organizer
    # builds the set up one rubric at a time (see the Rubric model docstring).
    total_weight = sum(c["weight"] for r in rubrics for c in r.criteria)
    if abs(total_weight - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This event's rubrics together must weight to 1.0 before judges can be assigned - "
            f"they currently add up to {total_weight:.4f}.",
        )

    submissions = list(
        session.exec(
            select(Submission).where(Submission.event_id == event_id, Submission.status == "submitted")
        )
    )
    if not submissions:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No submissions have been submitted for this event yet, so there is nothing to assign.",
        )
    judges = list(session.exec(select(User).where(User.role == Role.judge)))
    if not judges:
        raise HTTPException(status.HTTP_409_CONFLICT, "There are no judge accounts to assign.")

    team_ids = {s.team_id for s in submissions}
    memberships = list(session.exec(select(TeamMembership).where(TeamMembership.team_id.in_(team_ids))))

    proposed = assign_judges(submissions, judges, memberships, k=payload.judges_per_submission)

    existing = {
        (a.submission_id, a.judge_id)
        for a in session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event_id))
    }
    created = 0
    for assignment in proposed:
        if (assignment.submission_id, assignment.judge_id) in existing:
            continue
        session.add(assignment)
        created += 1
    record(
        session,
        "assignments.run",
        actor=user,
        entity_type="event",
        entity_id=event_id,
        created=created,
        judges_per_submission=payload.judges_per_submission,
    )
    session.commit()
    notify(session, background_tasks, event_id, "assignments.run", created=created)

    titles = {s.id: s.title for s in submissions}
    shortfall = coverage_report(submissions, proposed, k=payload.judges_per_submission)
    return AssignmentSummary(
        created=created,
        existing=len(proposed) - created,
        judges_per_submission=payload.judges_per_submission,
        coverage_warnings=[
            CoverageWarning(submission_id=sid, submission_title=titles.get(sid, ""), judges_short=short)
            for sid, short in sorted(shortfall.items())
        ],
    )


@router.get("/api/events/{event_id}/assignments", response_model=list[AssignmentPublic])
def list_assignments(
    event_id: int,
    _: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> list[AssignmentPublic]:
    """Organizer view of the whole matrix. Judges use /api/judge/assignments,
    which is scoped to themselves."""
    assignments = list(session.exec(select(JudgeAssignment).where(JudgeAssignment.event_id == event_id)))
    return _to_public(session, assignments)


# --------------------------------------------------------------------------
# Judge's own dashboard
# --------------------------------------------------------------------------

def _to_public(session: Session, assignments: list[JudgeAssignment]) -> list[AssignmentPublic]:
    if not assignments:
        return []
    scored = {
        s.assignment_id
        for s in session.exec(select(Score).where(Score.assignment_id.in_([a.id for a in assignments])))
    }
    rows: list[AssignmentPublic] = []
    for assignment in assignments:
        submission = session.get(Submission, assignment.submission_id)
        rows.append(
            AssignmentPublic(
                id=assignment.id,
                submission_id=assignment.submission_id,
                judge_id=assignment.judge_id,
                submission_title=(submission.title if submission else "") or "Untitled submission",
                scored=assignment.id in scored,
            )
        )
    rows.sort(key=lambda r: (r.scored, r.submission_id))
    return rows


@router.get("/api/judge/assignments", response_model=JudgeProgress)
def my_progress(
    user: User = Depends(require_role(Role.judge)),
    session: Session = Depends(get_session),
) -> JudgeProgress:
    """A judge sees only their own assignments -- never another judge's."""
    assignments = list(session.exec(select(JudgeAssignment).where(JudgeAssignment.judge_id == user.id)))
    rows = _to_public(session, assignments)
    done = [r for r in rows if r.scored]
    return JudgeProgress(completed=len(done), total=len(rows), pending=[r for r in rows if not r.scored], done=done)


@router.get("/api/assignments/{assignment_id}/sheet", response_model=ScoringSheet)
def scoring_sheet(
    assignment_id: int,
    user: User = Depends(require_role(Role.judge)),
    session: Session = Depends(get_session),
) -> ScoringSheet:
    """One call for the score form. Scoped to the owning judge, and it carries
    only this judge's own score -- never another judge's."""
    assignment = session.get(JudgeAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found.")
    if assignment.judge_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This submission is assigned to a different judge.")

    submission = session.get(Submission, assignment.submission_id)
    if not submission:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That submission no longer exists.")
    rubrics = _rubrics_for_event(session, assignment.event_id)
    if not rubrics:
        raise HTTPException(status.HTTP_409_CONFLICT, "This event has no rubric, so it cannot be scored yet.")

    mine = session.exec(select(Score).where(Score.assignment_id == assignment_id)).first()
    return ScoringSheet(
        assignment_id=assignment.id,
        submission_id=submission.id,
        submission_title=submission.title or "Untitled submission",
        submission_description=submission.description,
        submission_track=submission.track,
        rubrics=[RubricGroup(rubric_id=r.id, rubric_name=r.name, criteria=r.criteria) for r in rubrics],
        my_values=mine.values if mine else None,
        my_comment=mine.comment if mine else "",
        my_raw_total=mine.raw_total if mine else None,
    )


# --------------------------------------------------------------------------
# Signed judge participation records (PLAN.md Phase 4 T4) -- proof a judge
# took part in an event, verifiable offline against the published public key
# without trusting this server again.
# --------------------------------------------------------------------------

@router.get("/api/public-key")
def public_key() -> dict:
    return {"algorithm": "ed25519", "public_key": crypto.public_key_b64}


@router.get("/api/events/{event_id}/judges/{judge_id}/participation-record")
def participation_record(
    event_id: int,
    judge_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """The judge themself, or an organizer/admin, may request this -- never
    another judge (it would leak how much another judge actually did)."""
    if user.id != judge_id and user.role not in (Role.organizer, Role.admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You may only request your own participation record.")
    event = _event_or_404(session, event_id)
    judge = session.get(User, judge_id)
    if not judge or judge.role != Role.judge:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No judge with that id on this event.")

    assignments = list(
        session.exec(
            select(JudgeAssignment).where(JudgeAssignment.event_id == event_id, JudgeAssignment.judge_id == judge_id)
        )
    )
    if not assignments:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This judge has no assignments on this event.")
    scored = len(
        session.exec(
            select(Score).where(Score.assignment_id.in_([a.id for a in assignments]))
        ).all()
    )
    payload = {
        "event_id": event_id,
        "event_name": event.name,
        "judge_id": judge_id,
        "judge_name": judge.name,
        "submissions_assigned": len(assignments),
        "submissions_scored": scored,
        "issued_at": utcnow().isoformat(),
    }
    return crypto.sign_record(payload)
