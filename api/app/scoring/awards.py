"""Winners and awards (PLAN.md Phase 10.6).

Every event configures prizes (Event.prize_config), but until this module
nothing linked a prize to the project that won it - an event ended without
saying who won. The organizer confirms each winner, starting from a suggestion
derived from the normalised standings; winners stay hidden until results are
revealed, through the same `may_see_results` gate as the standings themselves.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, get_current_user_optional, require_role
from ..db import get_session
from ..events.models import Event
from ..events.visibility import may_see_results
from ..submissions.models import Submission, in_competition
from ..teams.models import Team
from ..timeutil import utcnow
from .models import Award

router = APIRouter(tags=["awards"])

ORGANIZER = (Role.organizer, Role.admin)


def _prizes(event: Event) -> list[dict]:
    return [p for p in (event.prize_config or {}).get("prizes", []) if p.get("rank")]


def _track_for_prize(label: str, tracks: list[str]) -> Optional[str]:
    """The track a prize is for, if its label names one ("Best Developer Tool"
    -> "Developer Tools"). ponytail: name matching with a trailing-"s" trim; a
    prize worded differently from its track just gets no suggestion - the
    organizer still picks the winner, this only pre-fills the picker."""
    lowered = label.lower()
    for track in tracks:
        stem = track.lower().rstrip("s")
        if stem and stem in lowered:
            return track
    return None


def awards_by_submission(session: Session, submission_ids: list[int]) -> dict[int, list[str]]:
    """submission_id -> prize labels it won. Callers must only show these where
    results are visible."""
    if not submission_ids:
        return {}
    out: dict[int, list[str]] = {}
    for award in session.exec(select(Award).where(Award.submission_id.in_(submission_ids))):
        out.setdefault(award.submission_id, []).append(award.prize_rank)
    return out


class PrizeSlot(BaseModel):
    prize_rank: str
    reward: str
    submission_id: Optional[int] = None
    note: str = ""
    suggested_submission_id: Optional[int] = None
    track: Optional[str] = None


class Candidate(BaseModel):
    submission_id: int
    title: str
    team_name: str
    track: str
    rank: Optional[int] = None


class AwardsView(BaseModel):
    prizes: list[PrizeSlot]
    results_visible_to_public: bool
    candidates: list[Candidate]


def _event_or_404(session: Session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    return event


def _awards_view(session: Session, event: Event) -> AwardsView:
    from .router import _result_rows  # scoring.router imports this module

    standings = _result_rows(session, event.id)
    submissions = {
        s.id: s
        for s in session.exec(
            select(Submission).where(Submission.event_id == event.id, in_competition())
        )
    }
    teams = {t.id: t.name for t in session.exec(select(Team).where(Team.event_id == event.id))}
    rank_of = {r.submission_id: r.rank for r in standings}
    ordered = [r.submission_id for r in standings] + sorted(set(submissions) - set(rank_of))
    saved = {a.prize_rank: a for a in session.exec(select(Award).where(Award.event_id == event.id))}

    # Suggestions: overall prizes follow the standings in order, never
    # suggesting one project twice; a track prize suggests that track's best.
    ranked = [sid for sid in ordered if sid in rank_of]
    used: set[int] = set()
    slots: list[PrizeSlot] = []
    for prize in _prizes(event):
        label = prize["rank"]
        track = _track_for_prize(label, event.tracks or [])
        if track:
            suggestion = next((sid for sid in ranked if submissions[sid].track == track), None)
        else:
            suggestion = next((sid for sid in ranked if sid not in used), None)
            if suggestion is not None:
                used.add(suggestion)
        award = saved.get(label)
        slots.append(
            PrizeSlot(
                prize_rank=label,
                reward=prize.get("reward", ""),
                submission_id=award.submission_id if award else None,
                note=award.note if award else "",
                suggested_submission_id=suggestion,
                track=track,
            )
        )
    return AwardsView(
        prizes=slots,
        results_visible_to_public=may_see_results(event, None),
        candidates=[
            Candidate(
                submission_id=sid,
                title=submissions[sid].title or "Untitled submission",
                team_name=teams.get(submissions[sid].team_id, ""),
                track=submissions[sid].track,
                rank=rank_of.get(sid),
            )
            for sid in ordered
        ],
    )


@router.get("/api/events/{event_id}/awards", response_model=AwardsView)
def get_awards(
    event_id: int,
    _: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> AwardsView:
    return _awards_view(session, _event_or_404(session, event_id))


class AwardWrite(BaseModel):
    prize_rank: str
    submission_id: Optional[int] = None  # null clears the prize
    note: str = ""

    @field_validator("note")
    @classmethod
    def note_len(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 200:
            raise ValueError("Keep the note to 200 characters or fewer.")
        return v


@router.put("/api/events/{event_id}/awards", response_model=AwardsView)
def set_award(
    event_id: int,
    payload: AwardWrite,
    user: User = Depends(require_role(*ORGANIZER)),
    session: Session = Depends(get_session),
) -> AwardsView:
    event = _event_or_404(session, event_id)
    if payload.prize_rank not in {p["rank"] for p in _prizes(event)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This event has no prize by that name.")
    award = session.exec(
        select(Award).where(Award.event_id == event_id, Award.prize_rank == payload.prize_rank)
    ).first()
    if payload.submission_id is None:
        if award:
            session.delete(award)
    else:
        submission = session.get(Submission, payload.submission_id)
        if submission is None or submission.event_id != event_id or not submission.competing:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pick a submitted project from this event.")
        if award is None:
            award = Award(
                event_id=event_id, prize_rank=payload.prize_rank, submission_id=submission.id, awarded_by_id=user.id
            )
        award.submission_id = submission.id
        award.note = payload.note
        award.awarded_by_id = user.id
        award.updated_at = utcnow()
        session.add(award)
    record(
        session,
        "award.set" if payload.submission_id else "award.cleared",
        actor=user,
        entity_type="event",
        entity_id=event_id,
        prize_rank=payload.prize_rank,
        submission_id=payload.submission_id,
    )
    session.commit()
    return _awards_view(session, event)


class Winner(BaseModel):
    prize_rank: str
    reward: str
    submission_id: int
    title: str
    team_name: str
    note: str


class WinnersView(BaseModel):
    visible: bool
    winners: list[Winner]


@router.get("/api/events/{event_id}/winners", response_model=WinnersView)
def get_winners(
    event_id: int,
    user: "User | None" = Depends(get_current_user_optional),
    session: Session = Depends(get_session),
) -> WinnersView:
    """Public. Empty and `visible: false` until the reveal - withheld in the
    response itself, not merely hidden by the page (same rule as standings)."""
    event = _event_or_404(session, event_id)
    if not may_see_results(event, user):
        return WinnersView(visible=False, winners=[])
    rewards = {p["rank"]: p.get("reward", "") for p in _prizes(event)}
    order = list(rewards)
    winners: list[Winner] = []
    for award in session.exec(select(Award).where(Award.event_id == event_id)):
        submission = session.get(Submission, award.submission_id)
        if submission is None:
            continue
        team = session.get(Team, submission.team_id)
        winners.append(
            Winner(
                prize_rank=award.prize_rank,
                reward=rewards.get(award.prize_rank, ""),
                submission_id=submission.id,
                title=submission.title or "Untitled submission",
                team_name=team.name if team else "",
                note=award.note,
            )
        )
    winners.sort(key=lambda w: order.index(w.prize_rank) if w.prize_rank in order else len(order))
    return WinnersView(visible=True, winners=winners)
