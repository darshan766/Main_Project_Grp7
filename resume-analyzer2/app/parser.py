"""
Step 2 of the pipeline: pull structured fields out of the segmented text.
Fast path (regex/spaCy) handles well-structured fields.
Fuzzy path (LLM) is called separately in llm_client.py for implicit skill extraction.
"""

import re
import json
from pathlib import Path

from app.config import SKILLS_TAXONOMY_PATH

# --- Load spaCy model once at import time ---
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except Exception:
    # Falls back gracefully if the model isn't downloaded yet.
    # Run: python -m spacy download en_core_web_sm
    nlp = None


EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Candidate phone strings: digits with spaces, dots, dashes or brackets between them.
# We then validate the digit count, so formats like "+91 98765 43210" and
# "(555) 123-4567" both work and year ranges like "2020 - 2022" don't.
PHONE_CANDIDATE_REGEX = re.compile(r"(?<![\w@])\+?\(?\d[\d\s().-]{7,18}\d(?![\w@])")
LINKEDIN_REGEX = re.compile(r"(linkedin\.com/in/[a-zA-Z0-9\-_/%]+)", re.IGNORECASE)
YEAR_REGEX = re.compile(r"(?:19|20)\d{2}")

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_RANGE_REGEX = re.compile(
    rf"(?P<start>(?:{_MONTH}\s+)?(?:19|20)\d{{2}})\s*(?:-|–|—|to)\s*"
    rf"(?P<end>(?:{_MONTH}\s+)?(?:19|20)\d{{2}}|present|current|now|ongoing|till date)",
    re.IGNORECASE,
)


def find_phone(text: str):
    """Return the first phone-like string with 10-15 digits, or None."""
    for match in PHONE_CANDIDATE_REGEX.finditer(text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)
        if 10 <= len(digits) <= 15 and not YEAR_REGEX.fullmatch(digits[:4] + ""):
            # reject runs that are just several years written next to each other
            if len(re.findall(r"(?:19|20)\d{2}", candidate)) >= 2 and len(digits) <= 12 and " " in candidate and "+" not in candidate:
                continue
            return candidate
    return None


def load_skills_taxonomy() -> dict:
    """Loads the canonical skills list + synonym mapping from data/skills_taxonomy.json"""
    with open(SKILLS_TAXONOMY_PATH, "r") as f:
        return json.load(f)


SKILLS_TAXONOMY = load_skills_taxonomy()
ALL_SKILL_TERMS = {
    synonym.lower(): canonical
    for canonical, entry in SKILLS_TAXONOMY.items()
    for synonym in entry["synonyms"] + [canonical]
}


def _guess_name(contact_block: str):
    """
    Fallback when spaCy is unavailable or finds no PERSON: the name is almost
    always the first line — short, alphabetic, no digits/@/links.
    """
    for line in contact_block.strip().split("\n")[:3]:
        line = line.strip()
        words = line.split()
        if not (1 < len(words) <= 4):
            continue
        if any(ch.isdigit() for ch in line) or "@" in line or "http" in line.lower() or "|" in line:
            continue
        if all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words) and not any(
            w.lower() in {"resume", "curriculum", "vitae", "cv"} for w in words
        ):
            return line.title() if line.isupper() else line
    return None


def extract_contact(contact_block: str) -> dict:
    """Regex + spaCy NER for contact fields (with a heuristic name fallback)."""
    email_match = EMAIL_REGEX.search(contact_block)
    linkedin_match = LINKEDIN_REGEX.search(contact_block)

    name = None
    location = None
    if nlp:
        first_line = contact_block.strip().split("\n")[0] if contact_block.strip() else ""
        doc = nlp(first_line)
        for ent in doc.ents:
            if ent.label_ == "PERSON" and not name:
                name = ent.text

        location_doc = nlp(contact_block[:300])
        for ent in location_doc.ents:
            if ent.label_ == "GPE" and not location:
                location = ent.text

    if not name:
        name = _guess_name(contact_block)

    return {
        "name": name,
        "email": email_match.group(0) if email_match else None,
        "phone": find_phone(contact_block),
        "location": location,
        "linkedin": linkedin_match.group(0) if linkedin_match else None,
    }


_SKILL_PATTERNS = [
    # (?<!\w)/(?!\w) instead of \b so terms like "node.js" and "c++" behave
    (re.compile(rf"(?<![\w]){re.escape(term)}(?![\w])"), canonical)
    for term, canonical in ALL_SKILL_TERMS.items()
]


def extract_skills(full_text: str) -> dict:
    """Gazetteer match against the skills taxonomy. Returns categorized + canonicalized skills."""
    found = {"technical": set(), "soft": set(), "tools": set()}
    lower_text = full_text.lower()

    for pattern, canonical in _SKILL_PATTERNS:
        if pattern.search(lower_text):
            category = SKILLS_TAXONOMY[canonical]["category"]
            found.setdefault(category, set()).add(canonical)

    return {k: sorted(v) for k, v in found.items()}


_DEGREE_REGEX = re.compile(
    r"\b(b\.?\s?tech|m\.?\s?tech|b\.?\s?e\.?|m\.?\s?e\.?|b\.?\s?sc|m\.?\s?sc|b\.?\s?a\.?|m\.?\s?a\.?|"
    r"b\.?\s?com|m\.?\s?com|bca|mca|mba|bba|ph\.?\s?d|bachelor[s']*|master[s']*|diploma|doctorate|associate)\b",
    re.IGNORECASE,
)
_INSTITUTION_REGEX = re.compile(r"\b(university|college|institute|school|academy|polytechnic|iit|nit)\b", re.IGNORECASE)
_GPA_REGEX = re.compile(r"\b(?:c|s)?gpa\b[:\s]*(\d+(?:\.\d+)?)", re.IGNORECASE)
_PART_SPLIT = re.compile(r"\s[-–—|]\s|\s*\|\s*|,\s+|\s+at\s+|\s+from\s+", re.IGNORECASE)


def extract_education(education_block: str) -> list:
    """Pattern-based extraction of degree/institution/years from the Education section."""
    entries = []
    lines = [l.strip() for l in education_block.split("\n") if l.strip()]

    for i, line in enumerate(lines):
        if not _DEGREE_REGEX.search(line):
            continue

        years = [int(y) for y in YEAR_REGEX.findall(line)]
        # a single year on a degree line is the graduation year, not the start year
        start_year = years[0] if len(years) > 1 else None
        end_year = years[-1] if years else None

        parts = [p.strip() for p in _PART_SPLIT.split(line) if p and p.strip()]
        degree = next((p for p in parts if _DEGREE_REGEX.search(p)), line)
        institution = next((p for p in parts if _INSTITUTION_REGEX.search(p) and p != degree), None)
        if not institution and i + 1 < len(lines) and _INSTITUTION_REGEX.search(lines[i + 1]) and not _DEGREE_REGEX.search(lines[i + 1]):
            institution = _PART_SPLIT.split(lines[i + 1])[0].strip()
            if not years:
                nxt = [int(y) for y in YEAR_REGEX.findall(lines[i + 1])]
                if nxt:
                    start_year = nxt[0] if len(nxt) > 1 else None
                    end_year = nxt[-1]

        if institution:
            institution = re.sub(r"\s*\(?(?:19|20)\d{2}.*$", "", institution).strip(" .,-") or None

        gpa_match = _GPA_REGEX.search(line) or (_GPA_REGEX.search(lines[i + 1]) if i + 1 < len(lines) else None)
        gpa = float(gpa_match.group(1)) if gpa_match else None

        entries.append({
            "degree": re.sub(r"\s*\(?(?:19|20)\d{2}.*$", "", degree).strip() or degree,
            "institution": institution,
            "start_year": start_year,
            "end_year": end_year,
            "gpa": gpa,
        })
    return entries


def _split_title_company(text: str):
    """'Backend Developer - Northwind Labs' / 'Dev at Acme' / 'Dev, Acme' -> (title, company)."""
    text = text.strip(" -–—|,•")
    parts = [p.strip() for p in _PART_SPLIT.split(text, maxsplit=1) if p and p.strip()]
    if len(parts) == 2:
        return parts[0], parts[1]
    return (parts[0] if parts else text), None


def _is_bullet(line: str) -> bool:
    return line.lstrip().startswith(("-", "*", "•", "–"))


def _looks_like_heading(line: str) -> bool:
    words = line.split()
    return (
        not _is_bullet(line)
        and 1 <= len(words) <= 9
        and not line.rstrip().endswith((".", ";"))
        and line[:1].isupper()
    )


def extract_experience(experience_block: str) -> list:
    """
    Split the Experience section into jobs. An entry starts at a heading line
    (usually carrying a date range such as "2022 - Present"); the lines after it
    are its description. Previously every line starting with a capital letter
    became its own entry, which broke descriptions and the writing feedback.
    """
    lines = [l.strip() for l in experience_block.split("\n") if l.strip()]
    entries = []
    current = None

    def new_entry(title, company=None, start=None, end=None):
        entry = {"title": title, "company": company, "start_date": start, "end_date": end, "_desc": []}
        entries.append(entry)
        return entry

    i = 0
    while i < len(lines):
        line = lines[i]
        date_match = DATE_RANGE_REGEX.search(line)
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        next_has_date = bool(DATE_RANGE_REGEX.search(nxt)) and not _is_bullet(nxt) and len(nxt.split()) <= 12

        if date_match and not _is_bullet(line) and len(line.split()) <= 14:
            rest = (line[:date_match.start()] + " " + line[date_match.end():]).strip(" -–—|,()")
            start, end = date_match.group("start").strip(), date_match.group("end").strip()
            if current and current["start_date"] is None and not current["_desc"] and current["company"] is None and rest and not _is_bullet(rest):
                # "Title" line followed by "Company  2020 - 2022"
                current["company"] = rest
                current["start_date"], current["end_date"] = start, end
            else:
                title, company = _split_title_company(rest) if rest else ("Untitled role", None)
                current = new_entry(title, company, start, end)
        elif not _is_bullet(line) and _looks_like_heading(line) and next_has_date and (current is None or current["_desc"] or current["start_date"]):
            # title-only line whose dates are on the next line
            title, company = _split_title_company(line)
            current = new_entry(title, company)
        elif current is None:
            current = new_entry(*_split_title_company(line))
        else:
            current["_desc"].append(line.lstrip("-*•– ").strip() if _is_bullet(line) else line)
        i += 1

    result = []
    for e in entries:
        description = "\n".join(e.pop("_desc"))
        skills = extract_skills(f"{e['title']}\n{description}")
        result.append({
            **e,
            "description": description,
            "extracted_skills": skills.get("technical", []) + skills.get("tools", []),
        })
    return result


def extract_certifications(cert_block: str) -> list:
    return [line.strip().lstrip("-*•– ").strip() for line in cert_block.split("\n") if line.strip()]
