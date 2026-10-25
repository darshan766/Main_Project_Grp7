"""
All API endpoints for the Resume Analyzer service.
Processing here is synchronous for simplicity (MVP). Swap in a Celery/RQ
job queue later for production if PDF/OCR + LLM calls become a bottleneck.
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB
from app.extractors import extract_text, segment_sections
from app.normalizer import build_candidate_profile
from app.ats_scorer import score_resume
from app.jd_matcher import match_resume_to_jd
from app.feedback import get_feedback
from app.models import Resume, get_db
from app.schemas import (
    UploadResponse,
    CandidateProfile,
    ATSScoreResponse,
    JDMatchRequest,
    JDMatchResponse,
    FeedbackResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/resume/upload", response_model=UploadResponse)
def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    original_name = Path(file.filename or "").name          # never trust client paths ("../../x")
    file_extension = Path(original_name).suffix.lower()

    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{file_extension or 'unknown'}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Store under a random name: no path traversal, and two people uploading
    # "resume.pdf" no longer overwrite each other.
    saved_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{file_extension}"
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    written = 0
    try:
        with open(saved_path, "wb") as buffer:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:               # stop reading as soon as it's too big
                    raise HTTPException(400, f"File exceeds {MAX_FILE_SIZE_MB}MB limit.")
                buffer.write(chunk)

        if written == 0:
            raise HTTPException(400, "The uploaded file is empty.")

        # --- Run the pipeline synchronously ---
        try:
            raw_text = extract_text(str(saved_path), file_extension)
        except Exception:
            logger.warning("Could not read %s", original_name, exc_info=True)
            raise HTTPException(422, "We couldn't read that file. It may be corrupted or password-protected.")

        if len(raw_text.split()) < 20:
            raise HTTPException(
                422,
                "No readable text found. If this is a scanned or image-only resume, export a text-based PDF or upload a DOCX instead.",
            )

        profile = build_candidate_profile(raw_text)
        sections = segment_sections(raw_text)
        ats_result = score_resume(raw_text, sections, profile["contact"])
    except Exception:
        saved_path.unlink(missing_ok=True)
        raise

    resume = Resume(
        file_name=original_name,
        file_type=file_extension,
        raw_text=raw_text,
        parsed_json=profile,
        parsed_confidence=profile["parsed_confidence_score"],
        ats_score=ats_result["ats_score"],
        ats_issues=ats_result["issues"],
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return UploadResponse(resume_id=resume.id, message="Resume parsed successfully.")


@router.get("/resume/{resume_id}", response_model=CandidateProfile)
def get_resume_profile(resume_id: str, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(404, "Resume not found.")
    return resume.parsed_json


@router.get("/resume/{resume_id}/ats-score", response_model=ATSScoreResponse)
def get_ats_score(resume_id: str, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(404, "Resume not found.")
    return ATSScoreResponse(ats_score=resume.ats_score, issues=resume.ats_issues or [])


@router.post("/resume/{resume_id}/match-jd", response_model=JDMatchResponse)
def match_jd(resume_id: str, request: JDMatchRequest, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(404, "Resume not found.")

    result = match_resume_to_jd(resume.parsed_json["skills"], request.jd_text)
    return JDMatchResponse(**result)


@router.get("/resume/{resume_id}/feedback", response_model=FeedbackResponse)
def get_resume_feedback(resume_id: str, db: Session = Depends(get_db)):
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(404, "Resume not found.")

    suggestions = get_feedback(resume.parsed_json)
    return FeedbackResponse(suggestions=suggestions)
