"""Embeddable gallery widget (DOGFOOD T4).

One self-contained HTML page per event, meant for an <iframe> on an organizer's
own site. Server-rendered with inline CSS and no script, so it needs nothing
from the SPA bundle and has nothing to break on someone else's page. The data
is exactly the public /api/gallery response for an anonymous visitor, so vote
counts and awards stay withheld while results are hidden.

This is the only path the app lets other sites frame (see main.py).
"""
from html import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from .db import get_session
from .events.models import Event
from .submissions.router import gallery

router = APIRouter(include_in_schema=False)

_CSS = """
:root{--bg:#fff;--card:#f6f7f8;--ink:#1f2426;--muted:#5b6469;--line:#e3e6e8;--brand:#0b7a55}
@media (prefers-color-scheme:dark){:root{--bg:#121516;--card:#1c2022;--ink:#eef1f2;--muted:#a3adb2;--line:#2c3235;--brand:#3ddc84}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--ink);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:12px}
h1{font-size:18px;margin:0}a{color:var(--brand)}
ul{list-style:none;margin:0;padding:0;display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}
li{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
img{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;background:var(--line)}
.body{padding:12px;display:flex;flex-direction:column;gap:6px}
h2{font-size:15px;margin:0}h2 a{color:var(--ink);text-decoration:none}h2 a:hover{text-decoration:underline}
p{margin:0;color:var(--muted);font-size:13px}.tag{font-size:12px;color:var(--muted)}
.award{font-size:12px;font-weight:600;color:var(--brand)}.empty{color:var(--muted)}
footer{margin-top:12px;font-size:12px;color:var(--muted)}
"""


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    html = (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body>{body}</body></html>"
    )
    return HTMLResponse(html, status_code=status_code)


def _clip(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@router.get("/embed/events/{slug}", response_class=HTMLResponse)
def embed_gallery(slug: str, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    event = session.exec(select(Event).where(Event.slug == slug)).first()
    if event is None or event.status != "published":
        return _page("Not found", '<p class="empty">This gallery is not available.</p>', 404)

    items = gallery(request, event_id=event.id, q=None, order="recent", seed=None, user=None, session=session)
    cards = []
    for item in items:
        image = f'<img src="{escape(item.image_url)}" alt="" loading="lazy">' if item.image_url else ""
        awards = "".join(f'<span class="award">&#9733; {escape(a)}</span>' for a in item.awards)
        track = f'<span class="tag">{escape(item.track)}</span>' if item.track else ""
        cards.append(
            f"<li>{image}<div class=\"body\">"
            f'<h2><a href="/submissions/{item.id}" target="_blank" rel="noopener">{escape(item.title or "Untitled")}</a></h2>'
            f"{awards}{track}<p>{escape(_clip(item.description))}</p></div></li>"
        )
    grid = f"<ul>{''.join(cards)}</ul>" if cards else '<p class="empty">No projects submitted yet.</p>'
    body = (
        f'<header><h1>{escape(event.name)}</h1>'
        f'<a href="/events/{escape(event.slug)}/gallery" target="_blank" rel="noopener">Full gallery</a></header>'
        f"{grid}<footer>{len(cards)} project{'' if len(cards) == 1 else 's'} · Powered by HackFlow</footer>"
    )
    return _page(f"{event.name} - projects", body)
