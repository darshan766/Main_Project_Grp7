"""
Resume Quality / Feedback Generator — produces specific, actionable writing
suggestions (weak verbs, missing metrics, structure issues) via an LLM pass.
"""

import logging

from app.llm_client import generate_resume_feedback

logger = logging.getLogger(__name__)


WEAK_VERBS = ["responsible for", "worked on", "helped with", "involved in", "assisted with"]


def get_feedback(candidate_profile: dict) -> list:
    """
    Combines a fast rule-based pass (catches obvious weak phrasing without an
    LLM call) with an LLM pass for deeper, context-aware suggestions.
    """
    suggestions = _rule_based_feedback(candidate_profile)

    try:
        llm_suggestions = generate_resume_feedback(candidate_profile)
        suggestions.extend(llm_suggestions)
    except RuntimeError:
        # LLM not configured (no API key) — still return the rule-based feedback
        pass
    except Exception:
        # Network error, rate limit, bad key, odd response... the rule-based
        # feedback is still useful, so don't turn this into a 500.
        logger.warning("LLM feedback failed; returning rule-based feedback only", exc_info=True)

    seen, unique = set(), []
    for item in suggestions:
        key = (item["section"], item["suggestion"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _rule_based_feedback(candidate_profile: dict) -> list:
    """Cheap, deterministic checks that don't need an LLM call at all."""
    suggestions = []

    for entry in candidate_profile.get("experience", []):
        description = (entry.get("description") or "").lower()
        for weak_phrase in WEAK_VERBS:
            if weak_phrase in description:
                suggestions.append({
                    "section": f"Experience — {entry.get('title') or 'Untitled role'}",
                    "suggestion": f'Consider replacing weak phrasing like "{weak_phrase}" with a stronger '
                                   f'action verb (e.g. "led", "built", "designed", "optimized").',
                })

        if description and not any(char.isdigit() for char in description):
            suggestions.append({
                "section": f"Experience — {entry.get('title') or 'Untitled role'}",
                "suggestion": "No quantifiable metrics found — consider adding numbers "
                              "(e.g. % improvement, users impacted, time saved).",
            })

    return suggestions
