"""StorageService interface (PLAN.md Phase 6). LocalStorage is the only
implementation shipped -- see PLAN.md's Phase 6 header for why a
self-hosted, single-node hackathon judging platform has no need for
S3-compatible object storage or a CDN. A second implementation
(S3CompatibleStorage) is the documented production upgrade path and is
deliberately never built or tested here.

    StorageService
    ├── LocalStorage         <- implemented, used
    └── S3CompatibleStorage  <- interface only, future upgrade path
"""
from __future__ import annotations

import hashlib
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

_EXT_BY_CONTENT_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


def _looks_like(data: bytes, content_type: str) -> bool:
    """The file's own first bytes must match the type it claims. The declared
    Content-Type is the client's word; these magic numbers are the file's."""
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


class StorageError(Exception):
    """A rejected upload. Callers turn this into a 422 with the message
    as-is -- it is already written for the person uploading, not a log."""


class StorageService(ABC):
    @abstractmethod
    def save(self, data: bytes, content_type: str) -> str:
        """Validates and writes `data`, returning the key it was stored
        under. Never trusts a caller-supplied key or filename -- generates
        its own, so a client can't choose where its upload lands."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        ...

    @abstractmethod
    def url_for(self, key: str) -> str:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...


class LocalStorage(StorageService):
    """Writes under a Docker-volume-backed directory. Keys are random hex,
    never derived from client input, so a client can never choose or guess
    a path; `_resolve` additionally proves the resolved path never leaves
    `root`, so even a key crafted by a bug elsewhere in this codebase can't
    be turned into a traversal."""

    def __init__(self, root: "str | Path"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._root_resolved = self.root.resolve()

    def _resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self._root_resolved):
            raise StorageError("Invalid file key.")
        return candidate

    def save(self, data: bytes, content_type: str) -> str:
        if content_type not in _EXT_BY_CONTENT_TYPE:
            raise StorageError(f"Unsupported image type: {content_type or 'unknown'}. Use PNG, JPEG, WebP, or GIF.")
        if not data:
            raise StorageError("The uploaded file is empty.")
        if len(data) > MAX_UPLOAD_BYTES:
            raise StorageError(f"Image must be under {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.")
        if not _looks_like(data, content_type):
            raise StorageError("That file isn't a real image of the type it claims to be.")
        key = f"{uuid.uuid4().hex}{_EXT_BY_CONTENT_TYPE[content_type]}"
        self._resolve(key).write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise StorageError("File not found.")
        return path.read_bytes()

    def url_for(self, key: str) -> str:
        return f"/media/{key}"

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()


def checksum_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_UPLOAD_ROOT = os.getenv("UPLOAD_DIR", "uploads")
storage: StorageService = LocalStorage(_UPLOAD_ROOT)
