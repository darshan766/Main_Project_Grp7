"""
SQLAlchemy DB models — how resume data is persisted.
Kept minimal (SQLite-friendly) so it runs out of the box; swap DATABASE_URL
in config.py to point at Postgres later without changing this file.
"""

import uuid
from datetime import datetime

from sqlalchemy import Column, String, Float, Integer, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine

from app.config import DATABASE_URL

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, nullable=True)
    file_name = Column(String)
    file_type = Column(String(10))
    raw_text = Column(String)
    parsed_json = Column(JSON)          # the CandidateProfile as JSON
    parsed_confidence = Column(Float, default=0.0)
    ats_score = Column(Integer, nullable=True)
    ats_issues = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JDMatchReport(Base):
    __tablename__ = "jd_match_reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    resume_id = Column(String)
    jd_fit_score = Column(Integer)
    matched_skills = Column(JSON)
    missing_critical_skills = Column(JSON)
    missing_preferred_skills = Column(JSON)
    transferable_skills = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)


# --- Engine / session setup ---
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
