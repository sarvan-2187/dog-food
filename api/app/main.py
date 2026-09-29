"""FastAPI entry point: mounts routers and serves the built SPA."""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Python's mimetypes module doesn't know .woff2 on every platform/Python build,
# so self-hosted fonts (public/fonts/*.woff2) were served as text/plain until
# this was added — found live while verifying the font fix below.
mimetypes.add_type("font/woff2", ".woff2")

from .db import create_db_and_tables
from .protection import ProtectionMiddleware, SecurityHeadersMiddleware, TrustedProxyMiddleware
from .request_limit import RateLimitMiddleware
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
from .events.questions import router as questions_router
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
from .auth.api_keys import router as api_keys_router
from .embed import router as embed_router

logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(os.getenv("STATIC_DIR", "static"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    run_seed()
    yield


API_DESCRIPTION = """
**HackFlow by Hackathon Raptors**: the hackathon operations platform, API first.
Every action in the web app is an endpoint here.

**Authentication**

- *Browser*: the `session` cookie set by `POST /api/auth/login`.
- *Integrations*: an API key, sent as `Authorization: Bearer hf_...`. Organizers and admins
  create keys on the **Integrations** page (`POST /api/api-keys`). A key acts as its owner,
  with exactly the owner's role, and can be revoked at any time.

**Events out**: organizers subscribe an event to signed webhooks (`submission.submitted`,
`assignments.run`, `score.submitted`, `event.results_revealed`, `announcement.posted`).
Payloads are signed with Ed25519. Verify the signature against the key from
`GET /api/public-key`, fetched once and pinned, never the `public_key` copy inside the payload
(anyone can sign with their own key and put that key there). Each signed record carries a
unique `delivery_id` and an `issued_at`, so a receiver can drop duplicates and stale replays.
"""

app = FastAPI(
    title="HackFlow API",
    description=API_DESCRIPTION,
    version="1.0",
    contact={"name": "Hackathon Raptors", "url": "https://www.raptors.dev", "email": "hello@raptors.dev"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
)


# Added innermost first. A request meets security headers, then the global
# 200/minute limit (request_limit.py), then ProtectionMiddleware; so a
# rate-limited request is refused before it takes an in-flight slot, and every
# cheap 413/429/503/504 refusal still carries the security headers.
app.add_middleware(ProtectionMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
# Outermost: fixes request.client before any limiter reads it.
app.add_middleware(TrustedProxyMiddleware)


@app.middleware("http")
async def frame_policy(request: Request, call_next):
    """Clickjacking (THREAT-MODEL): no other site may frame HackFlow - a framed
    judge console or vote button can be overlaid and click-tricked. The one
    exception is the gallery widget, which exists to be framed and has no
    buttons that change anything."""
    response = await call_next(request)
    if request.url.path.startswith("/embed/"):
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
    else:
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return response


# Browser caching for static files. Without it every page load re-requested
# every font, image and script, ~30 requests, each counting towards the
# 200/minute limit (found in acceptance testing). Vite names /assets/ files by
# content hash, so they never change under the same URL; public/ files
# (fonts, images) keep their names, so they get a day; index.html is always
# revalidated so a deploy is picked up at once.
_IMMUTABLE = "public, max-age=31536000, immutable"
_STATIC_PREFIXES = ("/fonts/", "/images/", "/favicon")


@app.middleware("http")
async def cache_policy(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if response.status_code == 200 and "cache-control" not in response.headers:
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = _IMMUTABLE
        elif path.startswith(_STATIC_PREFIXES):
            response.headers["Cache-Control"] = "public, max-age=86400"
        elif not path.startswith(("/api/", "/embed/", "/media/", "/healthz", "/docs", "/redoc", "/openapi.json")):
            response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(recovery_router)
app.include_router(admin_users_router)
app.include_router(announcements_router)
app.include_router(questions_router)
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
app.include_router(api_keys_router)
app.include_router(embed_router)

if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    # Anything the SPA owns; anything the API owns must still 404 as JSON.
    # Without this guard the catch-all answers GET /api/typo with the SPA shell
    # and a 200, so a client mistake looks like a successful empty response.
    API_PREFIXES = ("api/", "embed/", "healthz", "docs", "redoc", "openapi.json")

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
