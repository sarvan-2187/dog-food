"""FastAPI entry point: mounts routers and serves the built SPA."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import create_db_and_tables
from .seed import run_seed

# Import every model module before create_db_and_tables() so SQLModel.metadata
# knows about every table (auth has no cross-package dependency; the others
# reference "users.id" / "events.id" / "teams.id" by string foreign key).
from .auth import models as _auth_models  # noqa: F401
from .events import models as _event_models  # noqa: F401
from .teams import models as _team_models  # noqa: F401
from .submissions import models as _submission_models  # noqa: F401

from .auth.router import router as auth_router
from .events.router import router as events_router
from .teams.router import router as teams_router
from .submissions.router import router as submissions_router

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


app.include_router(auth_router)
app.include_router(events_router)
app.include_router(teams_router)
app.include_router(submissions_router)

if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve the SPA shell for any non-API path so client routing works."""
        return FileResponse(STATIC_DIR / "index.html")
