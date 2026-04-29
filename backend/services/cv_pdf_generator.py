"""
backend/services/cv_pdf_generator.py
───────────────────────────────────────
Generate an ATS-friendly PDF CV from a cv_data dict.
Adapted from the user-supplied ReportLab template — fully dynamic.

Entry point:
    generate_pdf(cv_data: dict) -> bytes
    generate_pdf_filename(cv_data: dict) -> str
"""
from __future__ import annotations

import html
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

# ── Colour palette ────────────────────────────────────────────────────────────
ACCENT     = colors.HexColor("#1F4E79")
GRAY       = colors.HexColor("#595959")
LIGHT_GRAY = colors.HexColor("#AAAAAA")
BLACK      = colors.HexColor("#1A1A1A")

_COL_W = (4.5 * inch, 2.0 * inch)   # left / right column widths for two-col tables

# Education rows: date aligns to BOTTOM of degree text (single line each side)
_TABLE_STYLE = TableStyle([
    ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
    ("TOPPADDING",    (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
])

# Job rows: date aligns to TOP so it sits beside the title, not beside the location
_JOB_TABLE_STYLE = TableStyle([
    ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING",    (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ("LEFTPADDING",   (0, 0), (-1, -1), 0),
    ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
])


# ── Style catalogue ───────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    return {
        "name": ParagraphStyle(
            "name", fontName="Helvetica-Bold", fontSize=22,
            textColor=ACCENT, alignment=TA_CENTER,
            leading=30,       # explicit leading keeps the 22pt name from compressing
            spaceAfter=10,    # was 4 — too small; caused title_line to appear inside the name
        ),
        "title_line": ParagraphStyle(
            "title_line", fontName="Helvetica", fontSize=10,
            textColor=GRAY, alignment=TA_CENTER,
            spaceBefore=4,    # additional breathing room away from the name
            spaceAfter=4,
        ),
        "contact": ParagraphStyle(
            "contact", fontName="Helvetica", fontSize=8.5,
            textColor=GRAY, alignment=TA_CENTER, spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "section", fontName="Helvetica-Bold", fontSize=10,
            textColor=ACCENT, spaceBefore=10, spaceAfter=3,
        ),
        "job_sub": ParagraphStyle(
            "job_sub", fontName="Helvetica-Oblique", fontSize=8.5,
            textColor=LIGHT_GRAY, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9,
            textColor=BLACK, spaceAfter=5, leading=13,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName="Helvetica", fontSize=9,
            textColor=BLACK, spaceAfter=3, leading=13,
            leftIndent=12, firstLineIndent=-10,
        ),
        "skill_label": ParagraphStyle(
            "skill_label", fontName="Helvetica-Bold", fontSize=9,
            textColor=ACCENT, spaceBefore=4, spaceAfter=2,
        ),
        "proj_header": ParagraphStyle(
            "proj_header", fontName="Helvetica", fontSize=9.5,
            textColor=BLACK, spaceBefore=6, spaceAfter=2,
        ),
        "jh": ParagraphStyle(
            "jh", fontName="Helvetica", fontSize=10, textColor=BLACK,
        ),
        "jr": ParagraphStyle(
            "jr", fontName="Helvetica", fontSize=8.5,
            textColor=LIGHT_GRAY, alignment=TA_RIGHT,
        ),
        "el": ParagraphStyle(
            "el", fontName="Helvetica-Bold", fontSize=10, textColor=BLACK,
        ),
        "er": ParagraphStyle(
            "er", fontName="Helvetica", fontSize=8.5,
            textColor=LIGHT_GRAY, alignment=TA_RIGHT,
        ),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _e(s: object) -> str:
    """HTML-escape, handle None gracefully."""
    return html.escape(str(s or ""))


def _section(title: str, S: dict) -> list:
    return [
        Paragraph(title.upper(), S["section"]),
        HRFlowable(width="100%", thickness=1, color=ACCENT, spaceAfter=4),
    ]


def _bullet(text: str, S: dict) -> Paragraph:
    return Paragraph(f"•&nbsp;&nbsp;{_e(text)}", S["bullet"])


def _two_col_table(left_para: Paragraph, right_para: Paragraph) -> Table:
    t = Table([[left_para, right_para]], colWidths=_COL_W)
    t.setStyle(_TABLE_STYLE)
    return t


def _job_header(title: str, company: str, dates: str, location: str, S: dict) -> list:
    # Build left cell: title | company on line 1, location (if any) on line 2.
    # Keeping everything inside the table row avoids the floating-word problem.
    left_text = f"<b>{_e(title)}</b>  <font color='#AAAAAA'>|</font>  <i>{_e(company)}</i>"
    if location:
        left_text += (
            f"<br/><font size='8' color='#AAAAAA'><i>{_e(location)}</i></font>"
        )

    left  = Paragraph(left_text, S["jh"])
    right = Paragraph(_e(dates), S["jr"])

    # Use TOP alignment so the date sits beside the title line, not the location line
    t = Table([[left, right]], colWidths=_COL_W)
    t.setStyle(_JOB_TABLE_STYLE)
    return [t]


def _edu_header(degree: str, school: str, years: str, gpa: str, S: dict) -> list:
    left  = Paragraph(f"<b>{_e(degree)}</b>", S["el"])
    right = Paragraph(_e(years), S["er"])
    sub_parts = [_e(school)]
    if gpa:
        sub_parts.append(f"CGPA: {_e(gpa)}")
    sub = Paragraph("  &nbsp;|&nbsp;  ".join(sub_parts), S["job_sub"])
    return [_two_col_table(left, right), sub]


# ── Main builder ──────────────────────────────────────────────────────────────

def generate_pdf(cv_data: dict) -> bytes:
    """Build a fully dynamic ATS-friendly PDF and return its bytes."""
    buf        = io.BytesIO()
    S          = _styles()
    contact    = cv_data.get("contact") or {}
    is_fresher = bool(cv_data.get("is_fresher", False))
    full_name  = (contact.get("name") or "Resume").strip()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"{full_name} — CV",
        author=full_name,
    )
    story: list = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph(_e(full_name), S["name"]))

    tech_skills = (cv_data.get("skills") or {}).get("technical") or []
    work_exp    = cv_data.get("work_experience") or []

    title_parts: list[str] = []
    if work_exp and not is_fresher:
        title_parts.append(work_exp[0].get("title", ""))
    title_parts += [s for s in tech_skills[:4] if s]
    if title_parts:
        story.append(Paragraph("  |  ".join(_e(p) for p in title_parts), S["title_line"]))

    contact_parts: list[str] = []
    for key in ("email", "phone", "linkedin", "github", "portfolio", "location"):
        val = contact.get(key)
        if val:
            # Strip scheme for compactness (https://linkedin.com/in/x → linkedin.com/in/x)
            display = val.removeprefix("https://").removeprefix("http://")
            contact_parts.append(_e(display))
    if contact_parts:
        story.append(Paragraph("  |  ".join(contact_parts), S["contact"]))

    story.append(HRFlowable(width="100%", thickness=1.5, color=ACCENT, spaceAfter=6))

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = (cv_data.get("summary") or "").strip()
    if summary:
        story += _section("Professional Summary", S)
        story.append(Paragraph(_e(summary), S["body"]))

    # ── Work Experience (skip for freshers) ───────────────────────────────────
    if not is_fresher and work_exp:
        story += _section("Work Experience", S)
        for exp in work_exp:
            end   = "Present" if exp.get("currently_working") else (exp.get("end_date") or "")
            dates = f"{exp.get('start_date', '')} – {end}".strip(" –")
            story += _job_header(
                exp.get("title", ""), exp.get("company", ""),
                dates, exp.get("location", ""), S,
            )
            for b in (exp.get("bullets") or []):
                if b:
                    story.append(_bullet(b, S))

    # ── Education ─────────────────────────────────────────────────────────────
    education = cv_data.get("education") or []
    if education:
        story += _section("Education", S)
        for edu in education:
            start = edu.get("start_year", "")
            end   = edu.get("end_year", "")
            years = f"{start} – {end}".strip(" –") if (start or end) else ""
            story += _edu_header(
                edu.get("degree", ""), edu.get("institution", ""),
                years, edu.get("gpa", ""), S,
            )
            cw = (edu.get("relevant_coursework") or "").strip()
            if cw:
                story.append(Paragraph(
                    f"<i>Relevant Coursework:</i> {_e(cw)}", S["job_sub"],
                ))

    # ── Skills ────────────────────────────────────────────────────────────────
    skills = cv_data.get("skills") or {}
    tech   = [s for s in (skills.get("technical") or []) if s]
    soft   = [s for s in (skills.get("soft") or []) if s]
    if tech or soft:
        story += _section("Skills", S)
        if tech:
            story.append(Paragraph("Technical Skills", S["skill_label"]))
            chunk = 5
            for i in range(0, len(tech), chunk):
                story.append(_bullet(", ".join(tech[i:i + chunk]), S))
        if soft:
            story.append(Paragraph("Soft Skills", S["skill_label"]))
            story.append(_bullet(", ".join(soft), S))

    # ── Projects ──────────────────────────────────────────────────────────────
    projects = cv_data.get("projects") or []
    if projects:
        story += _section("Projects", S)
        for proj in projects:
            name  = proj.get("name", "")
            stack = proj.get("tech_stack", "")
            hdr   = f"<b>{_e(name)}</b>"
            if stack:
                hdr += f"  |  <i>{_e(stack)}</i>"
            story.append(Paragraph(hdr, S["proj_header"]))
            if proj.get("description"):
                story.append(_bullet(proj["description"], S))
            if proj.get("outcome"):
                story.append(_bullet(proj["outcome"], S))
            if proj.get("link"):
                story.append(Paragraph(f"<i>Link:</i> {_e(proj['link'])}", S["job_sub"]))

    # ── Certifications ────────────────────────────────────────────────────────
    certs = cv_data.get("certifications") or []
    if certs:
        story += _section("Certifications", S)
        for cert in certs:
            parts = [p for p in (cert.get("name"), cert.get("issuer"), cert.get("year")) if p]
            story.append(_bullet("  |  ".join(parts), S))

    # ── Achievements ──────────────────────────────────────────────────────────
    achievements = cv_data.get("achievements") or []
    if achievements:
        story += _section("Achievements & Awards", S)
        for ach in achievements:
            if ach.get("description"):
                story.append(_bullet(ach["description"], S))

    doc.build(story)
    return buf.getvalue()


def generate_pdf_filename(cv_data: dict) -> str:
    contact = cv_data.get("contact") or {}
    name    = (contact.get("name") or "Resume").strip().replace(" ", "_")
    return f"{name}_ATS_CV.pdf"
