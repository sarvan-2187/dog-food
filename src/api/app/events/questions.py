"""Organizer-defined custom questions (DOGFOOD T1: "plus organizer-defined
custom questions").

An event holds up to ten short-text questions on `Event.questions`. Teams answer
them on the submission form (Submission.answers, keyed by question id), judges
read the answers on the score sheet, and the public project page shows only the
ones the organizer ticked "show publicly". A required question blocks Submit,
never autosave.

A question someone has answered can't be deleted, since that would silently
drop the team's answer from the record; the organizer hides it instead. A hidden
question leaves the form, the score sheet and the project page, and stops being
required, but its answers stay in the exports.
"""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import Role, User, require_role
from ..db import get_session
from ..submissions.models import Submission
from .models import Event

router = APIRouter(tags=["questions"])

MAX_QUESTIONS = 10
MAX_PROMPT = 200


class QuestionWrite(BaseModel):
    # Omitted for a new question; the server gives it an id that never changes.
    id: Optional[str] = None
    prompt: str
    required: bool = False
    hidden: bool = False
    public: bool = False

    @field_validator("prompt")
    @classmethod
    def prompt_len(cls, v: str) -> str:
        v = " ".join(v.split())
        if not (1 <= len(v) <= MAX_PROMPT):
            raise ValueError(f"A question must be 1-{MAX_PROMPT} characters.")
        return v


class QuestionSet(BaseModel):
    questions: list[QuestionWrite]


def new_question_id() -> str:
    return "q_" + secrets.token_hex(4)


def visible_questions(event: Event) -> list[dict]:
    """The questions teams and judges see: everything not hidden, in order."""
    return [q for q in (event.questions or []) if not q.get("hidden")]


def answer_rows(event: Event, submission: Submission, *, public_only: bool = False) -> list[dict]:
    """(question_id, prompt, answer) for each visible question this entry
    answered. `public_only` is the project page: just the organizer's ticked ones."""
    answers = submission.answers or {}
    return [
        {"question_id": q["id"], "prompt": q["prompt"], "answer": answers[q["id"]]}
        for q in visible_questions(event)
        if answers.get(q["id"]) and (q.get("public") or not public_only)
    ]


def missing_required(event: Event, submission: Submission) -> list[str]:
    answers = submission.answers or {}
    return [q["prompt"] for q in visible_questions(event) if q.get("required") and not answers.get(q["id"], "").strip()]


def normalize_questions(
    incoming: list[QuestionWrite], existing: list[dict], answered: set[str]
) -> list[dict]:
    """Validate a full replacement list against what is saved. Raises
    HTTPException, so both the settings endpoint and event import can use it."""
    if len(incoming) > MAX_QUESTIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"An event can have at most {MAX_QUESTIONS} questions.")
    known = {q["id"] for q in existing}
    out: list[dict] = []
    for q in incoming:
        if q.id is not None and q.id not in known:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"This event has no question {q.id!r}.")
        out.append(
            {"id": q.id or new_question_id(), "prompt": q.prompt, "required": q.required, "hidden": q.hidden, "public": q.public}
        )
    ids = [q["id"] for q in out]
    if len(set(ids)) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Each question can only appear once.")
    removed = [q for q in existing if q["id"] not in ids and q["id"] in answered]
    if removed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Teams have already answered \"{removed[0]['prompt']}\", so it can't be deleted. Hide it instead.",
        )
    return out


def answered_ids(session: Session, event_id: int) -> set[str]:
    ids: set[str] = set()
    for answers in session.exec(select(Submission.answers).where(Submission.event_id == event_id)):
        ids.update(k for k, v in (answers or {}).items() if str(v).strip())
    return ids


@router.put("/api/events/{event_id}/questions", response_model=list[dict])
def set_questions(
    event_id: int,
    payload: QuestionSet,
    user: User = Depends(require_role(Role.organizer, Role.admin)),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Replace the event's question list in one go, in the order given."""
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found.")
    event.questions = normalize_questions(payload.questions, event.questions or [], answered_ids(session, event_id))
    session.add(event)
    record(
        session, "event.questions_updated", actor=user, entity_type="event", entity_id=event_id,
        count=len(event.questions),
    )
    session.commit()
    session.refresh(event)
    return event.questions
