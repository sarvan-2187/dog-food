"""Participation certificate rendering (PLAN.md Phase 4 T4).

Pure: takes plain data in, returns PDF bytes out, no DB access -- the router
is the only thing that knows how to fetch a submission's team/event/rank.
"""
import io

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def render_certificate(*, event_name: str, team_name: str, submission_title: str, rank: int | None) -> bytes:
    buffer = io.BytesIO()
    width, height = landscape(letter)
    pdf = canvas.Canvas(buffer, pagesize=landscape(letter))

    pdf.setLineWidth(2)
    pdf.rect(0.4 * inch, 0.4 * inch, width - 0.8 * inch, height - 0.8 * inch)

    pdf.setFont("Helvetica-Bold", 28)
    pdf.drawCentredString(width / 2, height - 1.8 * inch, "Certificate of Participation")

    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(width / 2, height - 2.5 * inch, event_name)

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(width / 2, height - 3.4 * inch, team_name)

    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(width / 2, height - 3.9 * inch, f'for the submission "{submission_title}"')

    if rank:
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawCentredString(width / 2, height - 4.5 * inch, f"Final rank: #{rank}")

    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawCentredString(width / 2, 0.9 * inch, "Issued by HackFlow")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


if __name__ == "__main__":
    pdf_bytes = render_certificate(
        event_name="HackFlow Hackathon 2026",
        team_name="Flake Finders",
        submission_title="Flake Finder",
        rank=2,
    )
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 500
    print("certificate self-check passed")
