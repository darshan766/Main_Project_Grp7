"""Regression tests for the parsing / scoring pipeline. Run with: pytest -q"""
import io
import os
import sys
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/resume_test.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient

from app.ats_scorer import score_resume
from app.extractors import _match_section_header, segment_sections
from app.jd_matcher import match_resume_to_jd
from app.main import app
from app.normalizer import _estimate_total_experience
from app.parser import extract_education, extract_experience, extract_skills, find_phone


# --- section headers ---
@pytest.mark.parametrize("line,expected", [
    ("Skills", "skills"), ("TECHNICAL SKILLS:", "skills"), ("Work Experience", "experience"),
    ("Education & Training", "education"),
    ("Strong communication skills", None), ("Led 5 projects", None), ("Experience with Docker", None),
])
def test_section_headers_are_whole_lines(line, expected):
    assert _match_section_header(line) == expected


def test_bullet_mentioning_skills_does_not_split_section():
    text = "Education\nB.Tech 2016 - 2020\nExperience\nDev - Acme 2020 - 2022\nImproved team skills\nBuilt things"
    sections = segment_sections(text)
    assert "Improved team skills" in sections["experience"]


# --- phones ---
@pytest.mark.parametrize("text", ["+91 98765 43210", "(555) 123-4567", "555-123-4567", "9876543210"])
def test_phone_formats(text):
    assert find_phone(f"Call {text} now") is not None


@pytest.mark.parametrize("text", ["2020 - 2022", "Jan 2020 2021 2022", "Chennai 2016 2018"])
def test_year_ranges_are_not_phones(text):
    assert find_phone(text) is None


# --- education ---
def test_gpa_with_trailing_period_does_not_crash():
    edu = extract_education("Bachelor of Arts, Delhi College 2019. GPA 3.8.")
    assert edu[0]["gpa"] == 3.8
    assert edu[0]["institution"] == "Delhi College"
    assert edu[0]["end_year"] == 2019 and edu[0]["start_year"] is None


# --- experience ---
def test_experience_splits_into_jobs_not_lines():
    block = (
        "Backend Developer - Northwind Labs 2022 - Present\n"
        "Responsible for building APIs in Python.\n- Worked on Docker deployments\n"
        "Junior Developer\nBrightside Tech Jan 2020 - Dec 2021\nHelped with Flask services."
    )
    jobs = extract_experience(block)
    assert [j["title"] for j in jobs] == ["Backend Developer", "Junior Developer"]
    assert jobs[0]["company"] == "Northwind Labs" and jobs[1]["company"] == "Brightside Tech"
    assert "Responsible for" in jobs[0]["description"]


def test_total_experience_merges_overlaps():
    jobs = [{"start_date": "2020", "end_date": "2022"}, {"start_date": "2021", "end_date": "2023"}]
    # 2020-01..2023-12 merged = 47 months (3.9 yrs); naive summing would give 5.8
    assert _estimate_total_experience(jobs) == 3.9


# --- skills ---
def test_ambiguous_words_do_not_create_skills():
    found = extract_skills("Handled the rest of the backlog and TF-IDF features")
    assert "REST API" not in found["technical"] and "TensorFlow" not in found["tools"]


# --- JD scoring ---
def test_jd_without_preferred_section_has_no_free_points():
    r = match_resume_to_jd({"technical": ["Java"], "tools": [], "soft": []}, "Required: Python, Django, Docker")
    assert r["jd_fit_score"] == 0


def test_jd_full_match_scores_100_even_without_preferred():
    r = match_resume_to_jd({"technical": ["Python", "Django"], "tools": [], "soft": []}, "Required: Python and Django")
    assert r["jd_fit_score"] == 100


def test_nice_to_have_marker_is_recognised():
    r = match_resume_to_jd({"technical": ["Python"], "tools": [], "soft": []}, "Python required.\nNice to have: Docker")
    assert "Docker" in r["missing_preferred_skills"]


# --- ATS ---
def test_normal_punctuation_does_not_fail_the_garbled_check():
    text = ("Jane Doe - jane@x.com - (555) 123-4567\n" + "- Built APIs; improved latency by 30%.\n" * 60)
    sections = {"education": "x", "experience": "x", "skills": "x"}
    result = score_resume(text, sections, {"email": "a", "phone": "b"})
    assert result["ats_score"] == 100


# --- API ---
client = TestClient(app)


def test_upload_rejects_bad_type_and_traversal_name():
    r = client.post("/api/resume/upload", files={"file": ("../../evil.exe", b"x", "application/octet-stream")})
    assert r.status_code == 400


def test_upload_rejects_oversized_file():
    r = client.post("/api/resume/upload", files={"file": ("big.pdf", b"0" * (6 * 1024 * 1024), "application/pdf")})
    assert r.status_code == 400 and "5MB" in r.json()["detail"]


def test_upload_corrupt_pdf_is_a_clean_error_not_500():
    r = client.post("/api/resume/upload", files={"file": ("bad.pdf", b"not really a pdf", "application/pdf")})
    assert r.status_code == 422


def test_jd_text_must_not_be_empty():
    r = client.post("/api/resume/does-not-matter/match-jd", json={"jd_text": ""})
    assert r.status_code == 422
