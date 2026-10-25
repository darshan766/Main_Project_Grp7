"""
Pydantic schemas — define the shape of data going in/out of the API.
These are what get returned as JSON responses.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class Contact(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None


class Education(BaseModel):
    degree: Optional[str] = None
    institution: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    gpa: Optional[float] = None


class Experience(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    extracted_skills: List[str] = []


class Project(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tech_stack: List[str] = []
    outcome: Optional[str] = None


class Skills(BaseModel):
    technical: List[str] = []
    soft: List[str] = []
    tools: List[str] = []


class CandidateProfile(BaseModel):
    """The canonical structured output of the whole parsing pipeline."""
    candidate_id: Optional[str] = None
    contact: Contact = Contact()
    summary: Optional[str] = None
    education: List[Education] = []
    experience: List[Experience] = []
    projects: List[Project] = []
    skills: Skills = Skills()
    certifications: List[str] = []
    total_experience_years: float = 0.0
    parsed_confidence_score: float = 0.0


class ATSScoreResponse(BaseModel):
    ats_score: int
    issues: List[str]


class JDMatchRequest(BaseModel):
    jd_text: str = Field(min_length=10, max_length=20000)


class JDMatchResponse(BaseModel):
    jd_fit_score: int
    matched_skills: List[str]
    missing_critical_skills: List[str]
    missing_preferred_skills: List[str]
    transferable_skills: List[str]


class FeedbackItem(BaseModel):
    section: str
    suggestion: str


class FeedbackResponse(BaseModel):
    suggestions: List[FeedbackItem]


class UploadResponse(BaseModel):
    resume_id: str
    message: str
