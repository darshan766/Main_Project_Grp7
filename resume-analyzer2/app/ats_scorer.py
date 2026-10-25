"""
ATS Compatibility Scorer — checks how well the resume would survive a real
Applicant Tracking System, independent of any specific job description.
"""

from app.config import ATS_MAX_SCORE

# Each check is worth an equal share of the total score by default.
CHECKS = [
    "has_standard_sections",
    "has_email",
    "has_phone",
    "reasonable_length",
    "no_excessive_special_chars",
]


def score_resume(raw_text: str, sections: dict, contact: dict) -> dict:
    """
    Runs all ATS checks and returns {"ats_score": int, "issues": [str, ...]}
    """
    issues = []
    passed = 0

    # 1. Standard section headers present
    required_sections = {"education", "experience", "skills"}
    present_sections = {k for k, v in sections.items() if v.strip()}
    if required_sections.issubset(present_sections):
        passed += 1
    else:
        missing = sorted(required_sections - present_sections)
        issues.append(f"Missing standard section(s): {', '.join(missing)}")

    # 2. Email present and parseable
    if contact.get("email"):
        passed += 1
    else:
        issues.append("No email address detected — ensure it's in the document body, not an image/header.")

    # 3. Phone present
    if contact.get("phone"):
        passed += 1
    else:
        issues.append("No phone number detected.")

    # 4. Reasonable length (rough proxy: word count for 1-2 pages)
    word_count = len(raw_text.split())
    if 250 <= word_count <= 1200:
        passed += 1
    else:
        issues.append(
            f"Resume length looks {'too short' if word_count < 250 else 'too long'} "
            f"({word_count} words) — aim for roughly 1-2 pages."
        )

    # 5. No garbled characters (sign of bad PDF extraction / tables / text boxes).
    # Ordinary punctuation is expected in a resume and must not count against it,
    # otherwise normal bullets, dates and email addresses trip this check.
    normal_punctuation = set(".,;:-–—()[]/@+&%'\"#|*•!?$=_")
    odd_chars = sum(1 for c in raw_text if not c.isalnum() and not c.isspace() and c not in normal_punctuation)
    if odd_chars / max(len(raw_text), 1) < 0.02:
        passed += 1
    else:
        issues.append("Unusual or garbled characters detected — check for tables, icons or text boxes that don't extract cleanly.")

    score = round((passed / len(CHECKS)) * ATS_MAX_SCORE)
    return {"ats_score": score, "issues": issues}
