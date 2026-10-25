"""
FastAPI entrypoint for the Resume Analyzer service.
Run with: uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routes import router
from app.models import init_db

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Resume Analyzer Service",
    description="Parses resumes, scores ATS compatibility, and matches against job descriptions.",
    version="0.1.0",
)

# Lets the frontend be opened from another origin during development
# (e.g. a static file server). Tighten allow_origins before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Serve the frontend at "/". Mounted last so /api, /docs and /health take priority.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
