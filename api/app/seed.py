"""Idempotent fixture seeding, run automatically on app startup.

Phase 0 has no models, so `SEEDERS` is empty and `run_seed()` is a no-op.
Each phase that adds a model appends its seeder here; a seeder must check for
existing rows before inserting so repeated boots never duplicate data.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session

from .db import engine

log = logging.getLogger("seed")

FIXTURES_DIR = Path(os.getenv("FIXTURES_DIR", "fixtures"))

# Populated by later phases, e.g. SEEDERS.append(seed_users)
SEEDERS: list[Callable[[Session], None]] = []


def load_fixture(name: str) -> list[dict]:
    """Read fixtures/<name>. Returns [] when the file is absent."""
    path = FIXTURES_DIR / name
    if not path.exists():
        log.warning("fixture %s not found, skipping", path)
        return []
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def run_seed() -> None:
    if not SEEDERS:
        log.info("no seeders registered, schema left empty")
        return
    with Session(engine) as session:
        for seeder in SEEDERS:
            seeder(session)
        session.commit()
    log.info("seeding complete (%d seeders)", len(SEEDERS))


def _self_check() -> None:
    """Smallest check that fails if the fixture/registry contract breaks.

    Run with: python -m app.seed  (from api/)
    """
    assert load_fixture("__definitely_missing__.json") == []

    calls: list[str] = []
    SEEDERS.append(lambda _session: calls.append("ran"))
    try:
        assert len(SEEDERS) == 1
        assert calls == []
    finally:
        SEEDERS.clear()
    assert SEEDERS == []
    print("seed self-check ok")


if __name__ == "__main__":
    _self_check()
