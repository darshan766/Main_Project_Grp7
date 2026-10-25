"""
Step 3 of the pipeline: take the raw extracted fields and normalize/assemble
them into the final CandidateProfile structure.
"""

import re
from datetime import date

from app.extractors import segment_sections
from app.parser import (
    EMAIL_REGEX,
    LINKEDIN_REGEX,
    find_phone,
    extract_contact,
    extract_skills,
    extract_education,
    extract_experience,
    extract_certifications,
)


def build_candidate_profile(raw_text: str) -> dict:
    """
    Runs the full extraction pipeline on cleaned resume text and returns
    a CandidateProfile-shaped dict (matches schemas.CandidateProfile).
    """
    sections = segment_sections(raw_text)

    contact = extract_contact(sections.get("contact", ""))
    _fill_missing_contact(contact, raw_text)
    skills = extract_skills(raw_text)  # run over full text, not just the skills section
    education = extract_education(sections.get("education", ""))
    experience = extract_experience(sections.get("experience", ""))
    certifications = extract_certifications(sections.get("certifications", ""))

    total_experience_years = _estimate_total_experience(experience)
    confidence_score = _estimate_confidence(contact, skills, education, experience)

    profile = {
        "contact": contact,
        "summary": sections.get("summary", "").strip() or None,
        "education": education,
        "experience": experience,
        "projects": [],  # populate via a similar extractor if a Projects section exists
        "skills": skills,
        "certifications": certifications,
        "total_experience_years": total_experience_years,
        "parsed_confidence_score": confidence_score,
    }
    return profile


def _fill_missing_contact(contact: dict, raw_text: str) -> None:
    """Email/phone/LinkedIn are sometimes in a header/footer or after the first section heading."""
    if not contact.get("email"):
        m = EMAIL_REGEX.search(raw_text)
        contact["email"] = m.group(0) if m else None
    if not contact.get("phone"):
        contact["phone"] = find_phone(raw_text)
    if not contact.get("linkedin"):
        m = LINKEDIN_REGEX.search(raw_text)
        contact["linkedin"] = m.group(0) if m else None


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _to_month_index(text, default_month):
    """'Jan 2020' / '2020' -> months since year 0. 'Present' -> today. Unparseable -> None."""
    if not text:
        return None
    t = text.strip().lower()
    if t in {"present", "current", "now", "ongoing", "till date"}:
        today = date.today()
        return today.year * 12 + today.month
    year = re.search(r"(?:19|20)\d{2}", t)
    if not year:
        return None
    month = _MONTHS.get(t[:3], default_month) if t[:3].isalpha() else default_month
    return int(year.group(0)) * 12 + month


def _estimate_total_experience(experience_entries: list) -> float:
    """
    Sum of the time covered by dated roles, with overlapping roles merged so
    concurrent jobs aren't double counted. (This used to be len(entries) * 0.5.)
    """
    spans = []
    for e in experience_entries:
        start = _to_month_index(e.get("start_date"), 1)
        end = _to_month_index(e.get("end_date"), 12)
        if start is not None and end is not None and end >= start:
            spans.append((start, end))
    if not spans:
        return 0.0

    spans.sort()
    merged = [list(spans[0])]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    months = sum(end - start for start, end in merged)
    return round(months / 12, 1)


def _estimate_confidence(contact: dict, skills: dict, education: list, experience: list) -> float:
    """
    Simple heuristic confidence score based on how many key fields were
    successfully extracted. Not a trained model — just a sanity signal for now.
    """
    checks = [
        bool(contact.get("name")),
        bool(contact.get("email")),
        bool(skills.get("technical")),
        bool(education),
        bool(experience),
    ]
    return round(sum(checks) / len(checks), 2)
