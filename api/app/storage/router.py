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
from .models import StoredFile
from .service import StorageError, checksum_of, storage

router = APIRouter(tags=["storage"])


def _upsert_stored_file(
    session: Session, owner_type: str, owner_id: int, key: str, content_type: str, size_bytes: int, checksum: str
) -> StoredFile:
    existing = session.exec(
        select(StoredFile).where(StoredFile.owner_type == owner_type, StoredFile.owner_id == owner_id)
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
