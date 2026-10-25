"""
Skill-Gap Analyzer — compares a candidate's extracted skills against a
target Job Description to find matched, missing, and transferable skills.
"""

from app.parser import extract_skills
from app.config import JD_CRITICAL_SKILL_WEIGHT, JD_PREFERRED_SKILL_WEIGHT

import re
from functools import lru_cache

# Matches the point where a JD switches from "must-have" to "nice-to-have" wording.
_PREFERRED_MARKER = re.compile(
    r"\b(preferred|nice[\s-]to[\s-]have|good[\s-]to[\s-]have|bonus|desirable|a plus|added advantage)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _get_embedding_model():
    """
    Loaded on first use instead of at import time, so the API starts instantly
    and a slow/offline model download can't block startup. Returns None if
    sentence-transformers or the model isn't available.
    """
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:
        return None


def parse_jd_skills(jd_text: str) -> dict:
    """
    Very simple heuristic JD parsing: treat everything after 'required'/'preferred'
    keywords as the relevant skill list, then run the same skill extractor on it.
    A production version would use a dedicated JD-parsing prompt via the LLM.
    """
    required_section = jd_text
    preferred_section = ""

    marker = _PREFERRED_MARKER.search(jd_text)
    if marker:
        required_section = jd_text[:marker.start()]
        preferred_section = jd_text[marker.start():]

    required_skills = extract_skills(required_section)
    preferred_skills = extract_skills(preferred_section) if preferred_section else {"technical": [], "soft": [], "tools": []}

    def flatten(skills_dict):
        return set(skills_dict.get("technical", []) + skills_dict.get("tools", []) + skills_dict.get("soft", []))

    return {
        "required": flatten(required_skills),
        "preferred": flatten(preferred_skills),
    }


def match_resume_to_jd(candidate_skills: dict, jd_text: str) -> dict:
    """
    Returns matched/missing/transferable skills plus a weighted JD-Fit Score.
    """
    jd_skills = parse_jd_skills(jd_text)
    candidate_flat = set(
        candidate_skills.get("technical", [])
        + candidate_skills.get("tools", [])
        + candidate_skills.get("soft", [])
    )

    matched = candidate_flat & (jd_skills["required"] | jd_skills["preferred"])
    missing_critical = jd_skills["required"] - candidate_flat
    missing_preferred = jd_skills["preferred"] - candidate_flat

    # Skills the candidate already has aren't "transferable" stand-ins
    transferable = _find_transferable_skills(candidate_flat - matched, missing_critical | missing_preferred)

    # Weighted score. Only groups that actually exist in the JD take part, and the
    # weights are renormalised — before, a JD with no "preferred" section handed
    # every candidate 30 free points, and one with no required section 70.
    parts = []
    if jd_skills["required"]:
        parts.append((_coverage_ratio(jd_skills["required"], candidate_flat), JD_CRITICAL_SKILL_WEIGHT))
    if jd_skills["preferred"]:
        parts.append((_coverage_ratio(jd_skills["preferred"], candidate_flat), JD_PREFERRED_SKILL_WEIGHT))
    total_weight = sum(w for _, w in parts)
    fit_score = round(sum(r * w for r, w in parts) / total_weight * 100) if total_weight else 0

    return {
        "jd_fit_score": fit_score,
        "matched_skills": sorted(matched),
        "missing_critical_skills": sorted(missing_critical),
        "missing_preferred_skills": sorted(missing_preferred),
        "transferable_skills": sorted(transferable),
    }


def _coverage_ratio(required_set: set, candidate_set: set) -> float:
    if not required_set:
        return 1.0  # nothing required means nothing missing
    return len(required_set & candidate_set) / len(required_set)


def _find_transferable_skills(candidate_skills: set, missing_skills: set, threshold: float = 0.6) -> set:
    """
    Uses sentence embeddings to flag candidate skills that are semantically close
    to a missing skill (e.g. candidate has "Flask", JD wants "Django").
    Falls back to no transferable-skill detection if the embedding model isn't available.
    """
    model = _get_embedding_model()
    if not model or not candidate_skills or not missing_skills:
        return set()

    transferable = set()
    candidate_list = list(candidate_skills)
    missing_list = list(missing_skills)

    candidate_embeddings = model.encode(candidate_list, convert_to_tensor=True)
    missing_embeddings = model.encode(missing_list, convert_to_tensor=True)

    similarity_matrix = util.cos_sim(candidate_embeddings, missing_embeddings)

    for i, candidate_skill in enumerate(candidate_list):
        for j, missing_skill in enumerate(missing_list):
            if similarity_matrix[i][j] >= threshold:
                transferable.add(candidate_skill)

    return transferable
