"""
backend/services/groq_cv_parser.py
────────────────────────────────────
Parse raw resume text into the CV Builder JSON schema using Groq.
Falls back to OpenAI gpt-4o-mini if Groq fails or is unconfigured.

Entry point: parse_resume_with_groq(text: str) -> dict
"""
from __future__ import annotations

import json
import logging

from backend.config import GROQ_API_KEY, OPENAI_API_KEY

_log = logging.getLogger(__name__)

# ── Default empty structure ───────────────────────────────────────────────────

_EMPTY: dict = {
    "is_fresher": False,
    "contact": {
        "name": None, "phone": None, "email": None,
        "linkedin": None, "github": None, "portfolio": None, "location": None,
    },
    "summary": "",
    "work_experience": [],
    "education": [],
    "skills": {"technical": [], "soft": []},
    "projects": [],
    "certifications": [],
    "achievements": [],
}

# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are an expert resume parser. Extract structured data from resume text and return "
    "it as a JSON object matching the schema exactly.\n\n"
    "STRICT RULES:\n"
    "1. Return ONLY valid JSON — no markdown, no backticks, no commentary.\n"
    "2. work_experience: Extract EVERY job, internship, freelance, or contract role. "
    "Missing any is a failure.\n"
    "3. bullets: Preserve achievement text verbatim including all numbers and percentages.\n"
    "4. is_fresher: true ONLY if zero work experience (fresh graduate / student with no jobs).\n"
    "5. skills.technical: Every tool, language, framework, and platform mentioned anywhere.\n"
    "6. All dates: 'Mon YYYY' format (e.g. 'Jan 2022'). end_date = 'Present' when currently_working=true.\n"
    "7. GPA: only if explicitly stated, format 'X.X / Y.Y'. Empty string otherwise.\n"
    "8. Use null for missing string fields. Use [] for missing array fields.\n"
    "9. IDs: exp_1, exp_2 ... / edu_1 ... / proj_1 ... / cert_1 ... / ach_1 ...\n"
    "10. CRITICAL — URLs: For linkedin, github, portfolio and project links, only extract the ACTUAL URL "
    "that appears verbatim in the resume text. If no real URL is present, return null. "
    "NEVER invent, guess, or use placeholder URLs like 'https://linkedin.com/in/username' or "
    "'https://github.com/username'. If unsure, return null."
)

_SCHEMA_BLOCK = """{
  "is_fresher": false,
  "contact": {
    "name": "Full Name",
    "phone": "+91 XXXXXXXXXX",
    "email": "email@example.com",
    "linkedin": null,
    "github": null,
    "portfolio": null,
    "location": "City, Country"
  },
  "summary": "professional summary paragraph",
  "work_experience": [
    {
      "id": "exp_1",
      "title": "Job Title",
      "company": "Company Name",
      "location": "City, Country",
      "start_date": "Jan 2022",
      "end_date": "Dec 2023",
      "currently_working": false,
      "bullets": ["Achievement 1 with numbers", "Achievement 2"]
    }
  ],
  "education": [
    {
      "id": "edu_1",
      "degree": "B.Tech in Computer Science",
      "institution": "University Name",
      "start_year": "2018",
      "end_year": "2022",
      "gpa": "8.5 / 10",
      "relevant_coursework": "Data Structures, Algorithms"
    }
  ],
  "skills": {
    "technical": ["Python", "SQL", "React"],
    "soft": ["Communication", "Leadership"]
  },
  "projects": [
    {
      "id": "proj_1",
      "name": "Project Name",
      "description": "One-line description of what it does",
      "tech_stack": "Python, React, PostgreSQL",
      "outcome": "Impact or result",
      "link": "https://github.com/... or null"
    }
  ],
  "certifications": [
    {
      "id": "cert_1",
      "name": "Certification Name",
      "issuer": "Google / Coursera / AWS",
      "year": "2023"
    }
  ],
  "achievements": [
    {
      "id": "ach_1",
      "description": "Award or recognition description"
    }
  ]
}"""


def _build_user_message(text: str) -> str:
    return (
        "Extract ALL information from this resume and return the JSON object "
        "matching this exact schema:\n\n"
        + _SCHEMA_BLOCK
        + "\n\nRESUME TEXT:\n---\n"
        + text
        + "\n---"
    )


# ── Validation / normalisation ────────────────────────────────────────────────

def _coerce(data: dict) -> dict:
    """Ensure every required key exists with the correct type."""
    import copy
    out = copy.deepcopy(_EMPTY)

    out["is_fresher"] = bool(data.get("is_fresher", False))
    out["summary"]    = str(data.get("summary") or "")

    _PLACEHOLDER_URLS = {
        "https://linkedin.com/in/username",
        "https://github.com/username",
        "https://portfolio.com",
        "linkedin.com/in/username",
        "github.com/username",
        "portfolio.com",
    }

    contact = data.get("contact") or {}
    for k in out["contact"]:
        val = contact.get(k)
        if val:
            v = str(val).strip()
            if v.lower() in _PLACEHOLDER_URLS:
                v = None
            out["contact"][k] = v or None
        else:
            out["contact"][k] = None

    for i, exp in enumerate(data.get("work_experience") or [], start=1):
        out["work_experience"].append({
            "id":                str(exp.get("id") or f"exp_{i}"),
            "title":             str(exp.get("title") or ""),
            "company":           str(exp.get("company") or ""),
            "location":          str(exp.get("location") or ""),
            "start_date":        str(exp.get("start_date") or ""),
            "end_date":          str(exp.get("end_date") or ""),
            "currently_working": bool(exp.get("currently_working", False)),
            "bullets":           [b for b in (exp.get("bullets") or []) if b],
        })

    for i, edu in enumerate(data.get("education") or [], start=1):
        out["education"].append({
            "id":                  str(edu.get("id") or f"edu_{i}"),
            "degree":              str(edu.get("degree") or ""),
            "institution":         str(edu.get("institution") or ""),
            "start_year":          str(edu.get("start_year") or ""),
            "end_year":            str(edu.get("end_year") or ""),
            "gpa":                 str(edu.get("gpa") or ""),
            "relevant_coursework": str(edu.get("relevant_coursework") or ""),
        })

    skills = data.get("skills") or {}
    out["skills"]["technical"] = [s for s in (skills.get("technical") or []) if s]
    out["skills"]["soft"]      = [s for s in (skills.get("soft") or []) if s]

    for i, proj in enumerate(data.get("projects") or [], start=1):
        out["projects"].append({
            "id":          str(proj.get("id") or f"proj_{i}"),
            "name":        str(proj.get("name") or ""),
            "description": str(proj.get("description") or ""),
            "tech_stack":  str(proj.get("tech_stack") or ""),
            "outcome":     str(proj.get("outcome") or ""),
            "link":        str(proj.get("link")).strip() if proj.get("link") else None,
        })

    for i, cert in enumerate(data.get("certifications") or [], start=1):
        out["certifications"].append({
            "id":     str(cert.get("id") or f"cert_{i}"),
            "name":   str(cert.get("name") or ""),
            "issuer": str(cert.get("issuer") or ""),
            "year":   str(cert.get("year") or ""),
        })

    for i, ach in enumerate(data.get("achievements") or [], start=1):
        out["achievements"].append({
            "id":          str(ach.get("id") or f"ach_{i}"),
            "description": str(ach.get("description") or ""),
        })

    return out


# ── Main entry point ──────────────────────────────────────────────────────────

def parse_resume_with_groq(text: str) -> dict:
    """
    Parse resume text → validated cv_data dict.
    Uses Groq (llama-3.1-8b-instant) with JSON mode.
    Falls back to OpenAI gpt-4o-mini on any failure.
    """
    truncated = text[:8000]
    user_msg  = _build_user_message(truncated)
    messages  = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",   "content": user_msg},
    ]

    # ── Try Groq ──────────────────────────────────────────────────────────────
    if GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=4096,
                messages=messages,
            )
            raw  = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            _log.info("[groq_cv_parser] Groq parse succeeded.")
            return _coerce(data)
        except Exception as exc:
            _log.warning("[groq_cv_parser] Groq failed (%s) — falling back to OpenAI.", exc)

    # ── OpenAI fallback ───────────────────────────────────────────────────────
    if not OPENAI_API_KEY:
        raise RuntimeError("Neither GROQ_API_KEY nor OPENAI_API_KEY is configured.")

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        temperature=0,
        messages=messages,
    )
    raw  = resp.choices[0].message.content.strip()
    data = json.loads(raw)
    _log.info("[groq_cv_parser] OpenAI fallback parse succeeded.")
    return _coerce(data)
