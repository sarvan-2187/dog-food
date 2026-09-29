"""Participation certificates (PLAN.md Phase 4 T4), verifiable by anyone.

Pure rendering: plain data in, PDF bytes out, no DB access. The router fetches
the team, members, rank and prizes.

Each certificate carries a serial, `HF-<submission id>-<tag>`, where the tag is
an HMAC of the submission id under the server's secret. It can't be guessed for
another submission, and `GET /api/certificates/<serial>` (the public /verify
page) recomputes it, so an employer or a university can check a certificate
without an account and without trusting the PDF.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import os
import re
from datetime import date
from typing import Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

_SECRET = os.getenv("SESSION_SECRET", "dev-only-not-a-real-secret").encode()
_SERIAL_RE = re.compile(r"^HF-(\d{1,9})-([0-9A-F]{10})$")

INK = HexColor("#1F2426")
MUTED = HexColor("#6F7678")
RULE = HexColor("#C9CCCC")


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
) -> bytes:
    buffer = io.BytesIO()
    width, height = landscape(letter)
    pdf = canvas.Canvas(buffer, pagesize=landscape(letter))
    pdf.setTitle(f"{event_name} certificate: {team_name}")
    pdf.setAuthor("HackFlow by Hackathon Raptors")
    cx = width / 2

    # Frame: a heavy outer rule and a hairline inside it.
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(3)
    pdf.rect(0.35 * inch, 0.35 * inch, width - 0.7 * inch, height - 0.7 * inch)
    pdf.setLineWidth(0.6)
    pdf.rect(0.5 * inch, 0.5 * inch, width - 1.0 * inch, height - 1.0 * inch)

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(cx, height - 1.05 * inch, "H A C K F L O W   ·   B Y   H A C K A T H O N   R A P T O R S")

    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawCentredString(cx, height - 1.75 * inch, "Certificate of Achievement" if prizes else "Certificate of Participation")

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(cx, height - 2.3 * inch, "This certifies that")

    # Members in the serif italic accent (the app's Playfair italic, closest core font).
    pdf.setFillColor(INK)
    names = ", ".join(members) if members else team_name
    y = height - 2.9 * inch
    for line in simpleSplit(names, "Times-BoldItalic", 26, width - 2.6 * inch)[:3]:
        pdf.setFont("Times-BoldItalic", 26)
        pdf.drawCentredString(cx, y, line)
        y -= 0.42 * inch

    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(cx, y - 0.05 * inch, f"of team {team_name}, took part in")
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(cx, y - 0.45 * inch, event_name)
    if event_dates:
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(cx, y - 0.75 * inch, event_dates)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Oblique", 12)
    pdf.drawCentredString(cx, y - 1.1 * inch, f'with the project "{submission_title}"')

    highlight = []
    if prizes:  # PLAN.md 10.6 - the award itself, not just the rank
        highlight.append("Winner: " + ", ".join(prizes))
    if rank:
        highlight.append(f"Final rank #{rank}")
    if highlight:
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawCentredString(cx, y - 1.55 * inch, "  ·  ".join(highlight))

    # Footer: issue date left, verification right, organizer line centred.
    pdf.setStrokeColor(RULE)
    pdf.setLineWidth(0.6)
    pdf.line(1.0 * inch, 1.35 * inch, width - 1.0 * inch, 1.35 * inch)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(1.0 * inch, 1.1 * inch, f"Issued {(issued_on or date.today()).strftime('%d %B %Y')}")
    if serial:
        pdf.drawRightString(width - 1.0 * inch, 1.1 * inch, f"Certificate {serial}")
    if verify_url:
        pdf.drawRightString(width - 1.0 * inch, 0.92 * inch, f"Verify at {verify_url}")
    pdf.drawCentredString(cx, 0.72 * inch, "Hackathon Raptors CIC 15557917  ·  raptors.dev  ·  hello@raptors.dev")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


if __name__ == "__main__":
    s = certificate_serial(42)
    assert submission_for_serial(s) == 42
    assert submission_for_serial(s.lower()) == 42, "serials are case-insensitive"
    assert submission_for_serial("HF-43-" + s.split("-")[2]) is None, "a tag is bound to its submission"
    assert submission_for_serial("nonsense") is None
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
    )
    assert pdf_bytes.startswith(b"%PDF-")
    print("certificate self-check passed")
