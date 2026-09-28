"""FastAPI entry point: mounts routers and serves the built SPA."""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Python's mimetypes module doesn't know .woff2 on every platform/Python build,
# so self-hosted fonts (public/fonts/*.woff2) were served as text/plain until
# this was added — found live while verifying the font fix below.
mimetypes.add_type("font/woff2", ".woff2")

from .db import create_db_and_tables
from .seed import run_seed

# Import every model module before create_db_and_tables() so SQLModel.metadata
# knows about every table (auth has no cross-package dependency; the others
# reference "users.id" / "events.id" / "teams.id" by string foreign key).
from .auth import models as _auth_models  # noqa: F401
from .events import models as _event_models  # noqa: F401
from .teams import models as _team_models  # noqa: F401
from .submissions import models as _submission_models  # noqa: F401
from .judging import models as _judging_models  # noqa: F401
from .scoring import models as _scoring_models  # noqa: F401
from .voting import models as _voting_models  # noqa: F401
from .audit import models as _audit_models  # noqa: F401
from .storage import models as _storage_models  # noqa: F401
from .webhooks import models as _webhooks_models  # noqa: F401

from .auth.router import router as auth_router
from .auth.recovery import router as recovery_router
from .auth.admin_users import router as admin_users_router
from .events.announcements import router as announcements_router
from .judging.event_judges import router as event_judges_router
from .scoring.awards import router as awards_router
from .events.router import router as events_router
from .teams.router import router as teams_router
from .submissions.router import router as submissions_router
from .judging.router import router as judging_router
from .judging.invites import router as judge_invites_router
from .scoring.router import router as scoring_router
from .voting.router import router as voting_router
from .audit.router import router as audit_router
from .storage.router import router as storage_router
from .webhooks.router import router as webhooks_router

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(os.getenv("STATIC_DIR", "static"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    run_seed()
    yield


app = FastAPI(title="HackFlow", description="A HackRaptors hackathon judging platform.", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(recovery_router)
app.include_router(admin_users_router)
app.include_router(announcements_router)
app.include_router(event_judges_router)
app.include_router(awards_router)
app.include_router(events_router)
app.include_router(teams_router)
app.include_router(submissions_router)
app.include_router(judging_router)
app.include_router(judge_invites_router)
app.include_router(scoring_router)
app.include_router(voting_router)
app.include_router(audit_router)
app.include_router(storage_router)
app.include_router(webhooks_router)

if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # Anything the SPA owns; anything the API owns must still 404 as JSON.
    # Without this guard the catch-all answers GET /api/typo with the SPA shell
    # and a 200, so a client mistake looks like a successful empty response.
    API_PREFIXES = ("api/", "healthz", "docs", "redoc", "openapi.json")

    STATIC_DIR_RESOLVED = STATIC_DIR.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve a real static file if one exists at this path (e.g. anything
        Vite copied verbatim from web/public/, like /fonts/*.woff2 — found live
        while wiring self-hosted fonts: only /assets/* was mounted, so every
        other public/ file silently fell through to the SPA shell instead of
        being served). Otherwise serve the SPA shell so client routing works.

        full_path is attacker-controlled, so the resolved candidate must stay
        inside STATIC_DIR before it's served — otherwise a "../../etc/passwd"
        style path could read anything else in the container.
        """
        if full_path.startswith(API_PREFIXES):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such endpoint.")
        candidate = (STATIC_DIR / full_path).resolve()
        if candidate.is_relative_to(STATIC_DIR_RESOLVED) and candidate.is_file():
            return FileResponse(candidate)
        # A reset link carries its token in the path; never let it ride out in
        # a Referer header to anything the page loads (PLAN.md Phase 9.2).
        headers = {"Referrer-Policy": "no-referrer"} if full_path.startswith("reset/") else None
        return FileResponse(STATIC_DIR / "index.html", headers=headers)
