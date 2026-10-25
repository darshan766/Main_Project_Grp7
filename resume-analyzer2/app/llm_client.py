"""
Wrapper around the Claude API — keeps all LLM prompt logic in one place
so the rest of the codebase never constructs prompts directly.
"""

import json
import logging

import anthropic

from app.config import ANTHROPIC_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=30.0) if ANTHROPIC_API_KEY else None


def _parse_json_array(raw: str) -> list:
    """Models sometimes wrap JSON in prose or code fences; pull out the first JSON array."""
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return []
    return data if isinstance(data, list) else []


def _call_llm(prompt: str) -> str:
    """Low-level call — returns raw text response."""
    if client is None:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it as an environment variable "
            "to enable LLM-assisted extraction and feedback."
        )
    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _without_contact_details(profile: dict) -> dict:
    """Name, email and phone aren't needed to judge writing quality, so don't send them to the API."""
    return {k: v for k, v in profile.items() if k != "contact"}


def infer_implicit_skills(project_or_experience_text: str) -> list:
    """
    Fuzzy path: ask the LLM to infer skills mentioned implicitly in free text
    (e.g. "built a REST API in Flask" -> ["Flask", "REST API"]) that a simple
    keyword match might miss because of phrasing.
    """
    prompt = f"""Extract technical skills implied by this resume text, even if not
explicitly listed as a skill. Respond ONLY with a JSON array of skill strings,
nothing else.

Text:
{project_or_experience_text}
"""
    raw = _call_llm(prompt)
    return [s for s in _parse_json_array(raw) if isinstance(s, str)]


def generate_resume_feedback(candidate_profile_json: dict) -> list:
    """
    Generates specific, line-referenced writing feedback (weak verbs, missing
    quantification, structure issues) for the resume.
    Returns a list of {"section": ..., "suggestion": ...} dicts.
    """
    prompt = f"""You are reviewing a resume for writing quality (not skill content).
Given this structured resume data, list specific, actionable suggestions —
e.g. weak action verbs to strengthen, missing quantification/metrics, unclear
bullet points. Respond ONLY as a JSON array of objects with "section" and
"suggestion" keys. Keep each suggestion under 2 sentences.

Resume data:
{json.dumps(_without_contact_details(candidate_profile_json), indent=2)}
"""
    raw = _call_llm(prompt)
    suggestions = []
    for item in _parse_json_array(raw):
        if isinstance(item, dict) and isinstance(item.get("suggestion"), str) and item["suggestion"].strip():
            suggestions.append({
                "section": str(item.get("section") or "General"),
                "suggestion": item["suggestion"].strip(),
            })
    return suggestions
