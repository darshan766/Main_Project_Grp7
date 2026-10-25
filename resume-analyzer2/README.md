# Resume Analyzer Service

Parses resumes (PDF/DOCX), scores ATS compatibility, matches against job
descriptions, and generates writing feedback. Standalone microservice —
call its API from your main backend.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
python -m spacy download en_core_web_sm

# optional — enables LLM-assisted skill extraction + feedback
export ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive Swagger API docs.

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/resume/upload` | Upload a PDF/DOCX resume, returns `resume_id` |
| GET | `/api/resume/{resume_id}` | Get the full parsed CandidateProfile |
| GET | `/api/resume/{resume_id}/ats-score` | Get ATS compatibility score + issues |
| POST | `/api/resume/{resume_id}/match-jd` | Match resume against a job description |
| GET | `/api/resume/{resume_id}/feedback` | Get writing quality suggestions |

## Example: upload + match

```bash
curl -X POST http://localhost:8000/api/resume/upload \
  -F "file=@sample_resume.pdf"

# → { "resume_id": "abc-123", "message": "Resume parsed successfully." }

curl -X POST http://localhost:8000/api/resume/abc-123/match-jd \
  -H "Content-Type: application/json" \
  -d '{"jd_text": "Required: Python, Django, PostgreSQL. Preferred: Docker, AWS."}'
```

## Tests

```bash
pip install pytest httpx
pytest -q tests
```

## Notes on this MVP version

- **Processing is synchronous** for simplicity. If PDF/OCR + LLM calls become
  a bottleneck, add a Celery/RQ job queue and make `/upload` return
  immediately with a `job_id`, polled via a `/status` endpoint.
- **LLM features degrade gracefully.** If `ANTHROPIC_API_KEY` isn't set,
  the service still works — you just lose LLM-assisted implicit skill
  extraction and the deeper feedback pass (rule-based feedback still runs).
- **Skills taxonomy lives in `data/skills_taxonomy.json`** — edit this file
  to add new skills/synonyms without touching code.
- **Database defaults to SQLite** (zero setup). Set `DATABASE_URL` in your
  environment to point at Postgres for production.

## Integrating into your main project

This is designed to run as an independent service. Your main backend just
calls its HTTP API (e.g. `http://resume-service:8000/api/...`). No shared
code or imports needed — deploy it alongside your other services (Docker
Compose / Kubernetes) and point your main app's config at its base URL.

## Frontend

A static frontend lives in `frontend/` (plain HTML/CSS/JS, no build step) and is
served by the same FastAPI app, so after `uvicorn app.main:app --reload` just open
`http://localhost:8000`.

To host the frontend elsewhere, open `index.html?api=http://localhost:8000`
(CORS is enabled in `app/main.py`; restrict `allow_origins` before deploying).
