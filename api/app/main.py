"""FastAPI entry point: mounts routers and serves the built SPA."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import create_db_and_tables
from .seed import run_seed

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(os.getenv("STATIC_DIR", "static"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    run_seed()
    yield


app = FastAPI(title="Dogfood 2026", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Phase 1+ routers mount here, above the SPA catch-all below.

if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve the SPA shell for any non-API path so client routing works."""
        return FileResponse(STATIC_DIR / "index.html")
