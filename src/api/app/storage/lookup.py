"""Read helper for other routers that show an uploaded image without owning
the storage package themselves (the gallery, submission detail, auth)."""
from sqlmodel import Session, select

from .models import StoredFile
from .service import storage


def images_for(session: Session, owner_type: str, owner_id: int) -> list[StoredFile]:
    """Every image this owner has, in gallery order. A submission's first is its
    thumbnail (DOGFOOD T1); an avatar is always a list of one."""
    return list(
        session.exec(
            select(StoredFile)
            .where(StoredFile.owner_type == owner_type, StoredFile.owner_id == owner_id)
            .order_by(StoredFile.position)
        )
    )


def image_url_for(session: Session, owner_type: str, owner_id: int) -> "str | None":
    rows = images_for(session, owner_type, owner_id)
    return storage.url_for(rows[0].key) if rows else None


def image_list_for(session: Session, owner_type: str, owner_id: int) -> list[dict]:
    return [{"id": row.id, "url": storage.url_for(row.key)} for row in images_for(session, owner_type, owner_id)]


def image_urls_for(session: Session, owner_type: str, owner_ids: list[int]) -> dict[int, str]:
    """Batched form for a list view (the gallery) -- avoids one query per row."""
    if not owner_ids:
        return {}
    rows = session.exec(
        select(StoredFile)
        .where(StoredFile.owner_type == owner_type, StoredFile.owner_id.in_(owner_ids))
        .order_by(StoredFile.position.desc())
    ).all()
    # Descending, so each owner's first image (its thumbnail) is written last.
    return {row.owner_id: storage.url_for(row.key) for row in rows}
