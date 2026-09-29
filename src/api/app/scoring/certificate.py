"""Participation certificates (PLAN.md Phase 4 T4), verifiable by anyone.

Pure rendering: plain data in, PDF bytes out, no DB access. The router fetches
the team, members, rank and prizes.

Each certificate carries a serial, `HF-<submission id>-<tag>`, where the tag is
an HMAC of the submission id under the server's secret. It can't be guessed for
another submission, and `GET /api/certificates/<serial>` (the public /verify
page) recomputes it, so an employer or a university can check a certificate
without an account and without trusting the PDF.

An event picks one of `TEMPLATES`. Each is a background designed in Canva
(docs/CREDITS.md), shipped in certificate_templates/, plus the text colours and
the room its artwork leaves. Rendering stays local: no network call.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from ..auth.session import SESSION_SECRET

_SECRET = SESSION_SECRET.encode()
_SERIAL_RE = re.compile(r"^HF-(\d{1,9})-([0-9A-F]{10})$")
_BACKGROUNDS = Path(__file__).parent / "certificate_templates"


@dataclass(frozen=True)
class Template:
    """A certificate look. Positions are inches from the page edge."""

    label: str
    background: Optional[str] = None  # file in certificate_templates/; None draws a plain frame
    ink: str = "#1F2426"
    muted: str = "#6F7678"
    accent: str = "#1F2426"  # the title and the award line
    rule: str = "#C9CCCC"
    title_font: str = "Helvetica-Bold"
    centre: float = 0.5  # the content's horizontal centre, as a fraction of the width
    wrap: float = 8.4  # the widest a line of names may run
    top: float = 1.05  # the eyebrow's distance from the top edge
    footer: float = 1.35  # the footer rule's height
    footer_inset: float = 1.0  # footer text's distance from the left and right edges
    gap: float = 0.0  # a break in the middle of the footer rule, for a seal or ribbon


TEMPLATES: dict[str, Template] = {
    "classic": Template("Classic"),
    "gold": Template("Classic gold", "gold.jpg", ink="#3B2F1E", muted="#7A6A4F", accent="#8A6A1F",
                     rule="#C8B07A", top=1.2, footer=1.45, footer_inset=1.25, gap=2.4),
    "midnight": Template("Midnight tech", "midnight.jpg", ink="#EAF6FF", muted="#8FB3D1", accent="#5CE1E6",
                         rule="#2C4A6B", wrap=7.6, top=1.15, footer_inset=1.5),
    "gradient": Template("Modern gradient", "gradient.jpg", ink="#2A1F2D", muted="#7A6A78", accent="#D63B6F",
                         rule="#EBC9D6", top=1.35, footer=2.3, footer_inset=2.0),
    "emerald": Template("Emerald prestige", "emerald.jpg", ink="#123A2A", muted="#5F7A6D", accent="#0F5A3C",
                        rule="#C8B07A", top=1.2, footer=2.1, footer_inset=1.1, gap=3.6),
    "mono": Template("Minimal mono", "mono.jpg", ink="#111111", muted="#666666", accent="#111111",
                     rule="#BBBBBB", wrap=7.4, top=1.75, footer=1.95, footer_inset=2.4),
    "royal": Template("Royal blue", "royal.jpg", ink="#0F2350", muted="#5A6B8C", accent="#1D4ED8",
                      rule="#C3CCE0", centre=0.57, wrap=7.0, top=1.1, footer=1.4, footer_inset=1.9),
    "pixel": Template("Retro pixel", "pixel.jpg", ink="#2B2B2B", muted="#6B6B6B", accent="#D2452B",
                      rule="#E0CFA8", title_font="Courier-Bold", wrap=7.8, top=1.2, footer=1.4, footer_inset=1.9),
}


def certificate_serial(submission_id: int) -> str:
    tag = hmac.new(_SECRET, f"certificate:{submission_id}".encode(), hashlib.sha256).hexdigest()[:10].upper()
    return f"HF-{submission_id}-{tag}"


def submission_for_serial(serial: str) -> Optional[int]:
    """The submission a serial belongs to, or None if it is malformed or forged."""
    m = _SERIAL_RE.match(serial.strip().upper())
    if not m:
        return None
    submission_id = int(m.group(1))
    return submission_id if hmac.compare_digest(certificate_serial(submission_id), serial.strip().upper()) else None


def render_certificate(
    *,
    event_name: str,
    team_name: str,
    submission_title: str,
    rank: int | None,
    prizes: list[str] | None = None,
    members: list[str] | None = None,
    event_dates: str = "",
    issued_on: date | None = None,
    serial: str = "",
    verify_url: str = "",
    template: str = "classic",
) -> bytes:
    t = TEMPLATES.get(template, TEMPLATES["classic"])
    ink, muted, accent = HexColor(t.ink), HexColor(t.muted), HexColor(t.accent)
    buffer = io.BytesIO()
    width, height = landscape(letter)
    pdf = canvas.Canvas(buffer, pagesize=landscape(letter))
    pdf.setTitle(f"{event_name} certificate: {team_name}")
    pdf.setAuthor("HackFlow by Hackathon Raptors")
    cx = width * t.centre

    if t.background:
        pdf.drawImage(str(_BACKGROUNDS / t.background), 0, 0, width, height)
    else:
        # Frame: a heavy outer rule and a hairline inside it.
        pdf.setStrokeColor(ink)
        pdf.setLineWidth(3)
        pdf.rect(0.35 * inch, 0.35 * inch, width - 0.7 * inch, height - 0.7 * inch)
        pdf.setLineWidth(0.6)
        pdf.rect(0.5 * inch, 0.5 * inch, width - 1.0 * inch, height - 1.0 * inch)

    top = height - t.top * inch
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(cx, top, "H A C K F L O W   ·   B Y   H A C K A T H O N   R A P T O R S")

    pdf.setFillColor(accent)
    pdf.setFont(t.title_font, 30)
    pdf.drawCentredString(cx, top - 0.7 * inch, "Certificate of Achievement" if prizes else "Certificate of Participation")

    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(cx, top - 1.25 * inch, "This certifies that")

    # Members in the serif italic accent (the app's Playfair italic, closest core font).
    pdf.setFillColor(ink)
    names = ", ".join(members) if members else team_name
    y = top - 1.85 * inch
    for line in simpleSplit(names, "Times-BoldItalic", 26, t.wrap * inch)[:3]:
        pdf.setFont("Times-BoldItalic", 26)
        pdf.drawCentredString(cx, y, line)
        y -= 0.42 * inch

    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(cx, y - 0.05 * inch, f"of team {team_name}, took part in")
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(cx, y - 0.45 * inch, event_name)
    if event_dates:
        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(cx, y - 0.75 * inch, event_dates)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica-Oblique", 12)
    pdf.drawCentredString(cx, y - 1.1 * inch, f'with the project "{submission_title}"')

    highlight = []
    if prizes:  # PLAN.md 10.6 - the award itself, not just the rank
        highlight.append("Winner: " + ", ".join(prizes))
    if rank:
        highlight.append(f"Final rank #{rank}")
    if highlight:
        pdf.setFillColor(accent)
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawCentredString(cx, y - 1.55 * inch, "  ·  ".join(highlight))

    # Footer: issue date and organizer left, verification right, leaving the
    # middle clear for a template's seal or ribbon.
    left, right, base = t.footer_inset * inch, width - t.footer_inset * inch, t.footer * inch
    pdf.setStrokeColor(HexColor(t.rule))
    pdf.setLineWidth(0.6)
    if t.gap:
        pdf.line(left, base, width / 2 - t.gap * inch / 2, base)
        pdf.line(width / 2 + t.gap * inch / 2, base, right, base)
    else:
        pdf.line(left, base, right, base)
    pdf.setFillColor(muted)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawString(left, base - 0.25 * inch, f"Issued {(issued_on or date.today()).strftime('%d %B %Y')}")
    pdf.drawString(left, base - 0.43 * inch, "Hackathon Raptors CIC 15557917  ·  raptors.dev")
    if serial:
        pdf.drawRightString(right, base - 0.25 * inch, f"Certificate {serial}")
    if verify_url:
        pdf.drawRightString(right, base - 0.43 * inch, f"Verify at {verify_url}")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


if __name__ == "__main__":
    s = certificate_serial(42)
    assert submission_for_serial(s) == 42
    assert submission_for_serial(s.lower()) == 42, "serials are case-insensitive"
    assert submission_for_serial("HF-43-" + s.split("-")[2]) is None, "a tag is bound to its submission"
    assert submission_for_serial("nonsense") is None
    for key, tpl in TEMPLATES.items():
        assert tpl.background is None or (_BACKGROUNDS / tpl.background).is_file(), f"{key}: background missing"
        pdf_bytes = render_certificate(
            event_name="HackFlow Hackathon 2026",
            team_name="Flake Finders",
            submission_title="Flake Finder",
            rank=2,
            prizes=["2nd Place"],
            members=["Jordan Participant", "Riley Participant"],
            event_dates="15 - 17 October 2026",
            serial=s,
            verify_url="http://localhost:8000/verify/" + s,
            template=key,
        )
        assert pdf_bytes.startswith(b"%PDF-")
        if os.getenv("CERT_PREVIEW_DIR"):  # write each template's sample, for thumbnails
            Path(os.environ["CERT_PREVIEW_DIR"], f"{key}.pdf").write_bytes(pdf_bytes)
    print("certificate self-check passed")
