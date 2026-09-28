"""Upload and serving endpoints (PLAN.md Phase 6). Public read, ownership-
checked write -- an uploaded submission screenshot or avatar is exactly as
public as the gallery/profile data it illustrates, so GET /media/{key}
carries no auth check; only the two upload endpoints do."""
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlmodel import Session, select

from ..audit.log import record
from ..auth import User, get_current_user
from ..db import get_session
from ..submissions.models import Submission
from ..teams.deps import require_team_member
from ..teams.models import Team
from ..timeutil import utcnow
from ..submissions.schemas import MAX_IMAGES, ImageOrder, SubmissionImage
from .lookup import image_list_for, images_for
from .models import StoredFile
from .service import StorageError, checksum_of, storage

router = APIRouter(tags=["storage"])


def _upsert_stored_file(
    session: Session, owner_type: str, owner_id: int, key: str, content_type: str, size_bytes: int, checksum: str
) -> StoredFile:
    """Replace this owner's image at position 0: an avatar, or a submission's
    first gallery image (its thumbnail)."""
    existing = session.exec(
        select(StoredFile).where(
            StoredFile.owner_type == owner_type, StoredFile.owner_id == owner_id, StoredFile.position == 0
        )
    ).first()
    if existing:
        storage.delete(existing.key)  # never orphan the superseded file on disk
        existing.key = key
        existing.content_type = content_type
        existing.size_bytes = size_bytes
        existing.checksum = checksum
        existing.created_at = utcnow()
        row = existing
    else:
        row = StoredFile(
            key=key,
            owner_type=owner_type,
            owner_id=owner_id,
            content_type=content_type,
            size_bytes=size_bytes,
            checksum=checksum,
        )
    session.add(row)
    return row


@router.post("/api/teams/{team_id}/submission/image")
async def upload_submission_image(
    team_id: int,
    file: UploadFile,
    team: Team = Depends(require_team_member),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """require_team_member already proves the caller is on this team; a
    submission's image can only ever be set by its own team, never another."""
    submission = session.exec(select(Submission).where(Submission.team_id == team_id)).first()
    if not submission:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Start a submission before adding an image.")
    data = await file.read()
    try:
        key = storage.save(data, file.content_type or "")
    except StorageError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    _upsert_stored_file(session, "submission", submission.id, key, file.content_type or "", len(data), checksum_of(data))
    record(session, "submission.image_uploaded", actor=user, entity_type="submission", entity_id=submission.id)
    session.commit()
    return {"image_url": storage.url_for(key)}


# --------------------------------------------------------------------------
# A submission's image gallery (DOGFOOD T1): up to five, in order, the first
# being the thumbnail. POST .../image above stays as "replace image 1", so an
# older client keeps working. Same checks as every upload (type, size, magic
# bytes, in storage.save), same rule that only the team can change them, and
# like the rest of the submission they are frozen once submissions close.
# --------------------------------------------------------------------------

def _team_submission_open(session: Session, team: Team) -> Submission:
    from ..submissions.router import _load_open_event  # local: that router imports storage.lookup

    _load_open_event(session, team.event_id)
    submission = session.exec(select(Submission).where(Submission.team_id == team.id)).first()
    if not submission:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Start a submission before adding an image.")
    return submission


def _renumber(session: Session, rows: list[StoredFile]) -> None:
    """Give `rows` positions 0..n-1 in list order. Two passes, through negative
    positions, so no intermediate state trips the unique (owner, position) key."""
    for i, row in enumerate(rows):
        row.position = -1 - i
        session.add(row)
    session.flush()
    for i, row in enumerate(rows):
        row.position = i
        session.add(row)
    session.flush()


@router.post("/api/teams/{team_id}/submission/images", response_model=list[SubmissionImage])
async def add_submission_image(
    team_id: int,
    file: UploadFile,
    team: Team = Depends(require_team_member),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Append one image to the end of the gallery."""
    submission = _team_submission_open(session, team)
    rows = images_for(session, "submission", submission.id)
    if len(rows) >= MAX_IMAGES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A project can have at most {MAX_IMAGES} images. Remove one first."
        )
    data = await file.read()
    try:
        key = storage.save(data, file.content_type or "")
    except StorageError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    session.add(
        StoredFile(
            key=key,
            owner_type="submission",
            owner_id=submission.id,
            position=len(rows),
            content_type=file.content_type or "",
            size_bytes=len(data),
            checksum=checksum_of(data),
        )
    )
    record(session, "submission.image_uploaded", actor=user, entity_type="submission", entity_id=submission.id)
    session.commit()
    return image_list_for(session, "submission", submission.id)


@router.delete("/api/teams/{team_id}/submission/images/{image_id}", response_model=list[SubmissionImage])
def remove_submission_image(
    team_id: int,
    image_id: int,
    team: Team = Depends(require_team_member),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Remove one image; the rest close up, so the next becomes the thumbnail."""
    submission = _team_submission_open(session, team)
    rows = images_for(session, "submission", submission.id)
    target = next((r for r in rows if r.id == image_id), None)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That image isn't on this project.")
    storage.delete(target.key)
    session.delete(target)
    session.flush()
    _renumber(session, [r for r in rows if r.id != image_id])
    record(
        session, "submission.image_removed", actor=user, entity_type="submission", entity_id=submission.id,
        image_id=image_id,
    )
    session.commit()
    return image_list_for(session, "submission", submission.id)


@router.put("/api/teams/{team_id}/submission/images/order", response_model=list[SubmissionImage])
def reorder_submission_images(
    team_id: int,
    payload: ImageOrder,
    team: Team = Depends(require_team_member),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Set the gallery order. The list must name every image exactly once."""
    submission = _team_submission_open(session, team)
    rows = {r.id: r for r in images_for(session, "submission", submission.id)}
    if sorted(payload.image_ids) != sorted(rows):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "List every image on this project exactly once, in the new order."
        )
    _renumber(session, [rows[i] for i in payload.image_ids])
    record(session, "submission.images_reordered", actor=user, entity_type="submission", entity_id=submission.id)
    session.commit()
    return image_list_for(session, "submission", submission.id)


@router.post("/api/users/me/avatar")
async def upload_avatar(
    file: UploadFile,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    data = await file.read()
    try:
        key = storage.save(data, file.content_type or "")
    except StorageError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    _upsert_stored_file(session, "user", user.id, key, file.content_type or "", len(data), checksum_of(data))
    session.commit()
    return {"avatar_url": storage.url_for(key)}


@router.get("/media/{key}")
def serve_media(key: str, session: Session = Depends(get_session)) -> Response:
    """Only ever serves a key that a StoredFile row still claims -- deleting
    the row (e.g. superseded by a new upload) makes the old key 404 even if
    the bytes briefly still exist on disk mid-replace."""
    row = session.exec(select(StoredFile).where(StoredFile.key == key)).first()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found.")
    try:
        data = storage.read(key)
    except StorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found.")
    return Response(
        content=data,
        media_type=row.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
