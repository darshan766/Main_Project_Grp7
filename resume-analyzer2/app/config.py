"""
Central configuration for the Resume Analyzer service.
Reads from environment variables where possible so nothing sensitive is hardcoded.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- File handling ---
MAX_FILE_SIZE_MB = 5
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# --- Skills taxonomy ---
SKILLS_TAXONOMY_PATH = BASE_DIR / "data" / "skills_taxonomy.json"

# --- LLM settings ---
# Set this in your environment: export ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'resume_service.db'}")

# --- Scoring weights ---
ATS_MAX_SCORE = 100
JD_CRITICAL_SKILL_WEIGHT = 0.7   # required skills matter more than nice-to-haves
JD_PREFERRED_SKILL_WEIGHT = 0.3
