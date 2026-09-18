"""Read helper for other routers that show an uploaded image without owning
the storage package themselves (the gallery, submission detail, auth)."""
from sqlmodel import Session, select

from .models import StoredFile
from .service import storage


def image_url_for(session: Session, owner_type: str, owner_id: int) -> "str | None":
    row = session.exec(
        select(StoredFile).where(StoredFile.owner_type == owner_type, StoredFile.owner_id == owner_id)
    ).first()
    return storage.url_for(row.key) if row else None


def image_urls_for(session: Session, owner_type: str, owner_ids: list[int]) -> dict[int, str]:
    """Batched form for a list view (the gallery) -- avoids one query per row."""
    if not owner_ids:
        return {}
    rows = session.exec(
        select(StoredFile).where(StoredFile.owner_type == owner_type, StoredFile.owner_id.in_(owner_ids))
    ).all()
    return {row.owner_id: storage.url_for(row.key) for row in rows}
