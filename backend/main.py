"""
JobFit — FastAPI Backend
Entry point. Runs the multi-agent analysis pipeline.
"""
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from agents.graph import run_analysis
from agents.resume_parser import parse_resume
from agents.jd_parser import parse_jd
from agents.outreach import draft_outreach, draft_follow_up
from agents.interview_prep import prep_interview
from scraper.search import search_jobs, JobFilters
from scraper.registry import all_companies
from scraper.contacts import discover_contacts
from scraper.recruiter_search import find_recruiters
from analytics.autopsy import run_autopsy
from utils.pdf_extractor import extract_text
import uvicorn, os, time
from collections import deque

app = FastAPI(title="JobFit API", version="1.0.0")

# Comma-separated list of allowed origins, e.g.
#   ALLOWED_ORIGINS=https://jobfit.vercel.app,http://localhost:5173
_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ── Input limits (guard against abuse / cost runaway) ────────
MAX_FILE_BYTES = int(os.getenv("MAX_FILE_BYTES", str(5 * 1024 * 1024)))  # 5 MB
MAX_JD_CHARS   = int(os.getenv("MAX_JD_CHARS", "20000"))
MAX_RESUME_CHARS = int(os.getenv("MAX_RESUME_CHARS", "20000"))

# ── Lightweight in-memory per-IP rate limit (single-instance) ─
# Each /analyze call fans out to 4 LLM requests, so cap how often one
# client can trigger it. For multi-instance deploys, move this to Redis.
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "10"))      # requests
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds
_hits: dict[str, deque] = {}

def _check_rate_limit(ip: str) -> None:
    now = time.time()
    q = _hits.setdefault(ip, deque())
    while q and now - q[0] > RATE_LIMIT_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT_MAX:
        raise HTTPException(429, "Too many requests. Please wait a moment and try again.")
    q.append(now)

@app.get("/")
def root():
    return {"status": "ok", "app": "JobFit", "version": "1.0.0"}

@app.get("/health")
def health():
    # Koyeb uses this for health checks
    return {"status": "healthy"}

async def _resolve_resume(resume_file: UploadFile, resume_text: str) -> str:
    """Pull resume text from an uploaded file or pasted text, with size guards."""
    if resume_file and resume_file.filename:
        file_bytes = await resume_file.read()
        if len(file_bytes) > MAX_FILE_BYTES:
            raise HTTPException(413, f"File too large (max {MAX_FILE_BYTES // (1024*1024)} MB).")
        raw = extract_text(file_bytes, resume_file.filename)
    elif resume_text and resume_text.strip():
        raw = resume_text.strip()[:MAX_RESUME_CHARS]
    else:
        raise HTTPException(400, "Provide a resume file or paste resume text.")

    if not raw.strip():
        raise HTTPException(400, "Could not read any text from the resume.")
    return raw


@app.post("/analyze")
async def analyze(
    request: Request,
    resume_file: UploadFile = File(None),
    resume_text: str = Form(None),
    job_description: str = Form(...)
):
    _check_rate_limit(request.client.host if request.client else "unknown")
    raw_resume = await _resolve_resume(resume_file, resume_text)

    if not job_description.strip():
        raise HTTPException(400, "Job description cannot be empty.")
    if len(job_description) > MAX_JD_CHARS:
        raise HTTPException(413, f"Job description too long (max {MAX_JD_CHARS} chars).")

    # ── Run the 4-agent LangGraph pipeline ──────────────────
    return await run_analysis(raw_resume, job_description)


@app.post("/jobs/search")
async def jobs_search(
    request: Request,
    resume_file: UploadFile = File(None),
    resume_text: str = Form(None),
    query: str = Form(""),
    location: str = Form(""),
    remote_only: bool = Form(False),
    domain: str = Form(""),
    experience: str = Form(""),
    posted_within_hours: int = Form(0),
    companies: str = Form(""),       # comma-separated registry slugs
    limit: int = Form(50),
):
    """
    Scrape + rank jobs against the resume. Ranking here is LLM-free (instant,
    free); the precise LLM gap score runs later via /analyze when a user opens
    a specific job to tailor their resume.
    """
    _check_rate_limit(request.client.host if request.client else "unknown")
    raw_resume = await _resolve_resume(resume_file, resume_text)

    filters = JobFilters(
        query=query.strip(),
        location=location.strip(),
        remote_only=remote_only,
        domain=domain.strip(),
        experience=experience.strip(),
        posted_within_hours=max(0, posted_within_hours),
        companies=[s.strip() for s in companies.split(",") if s.strip()],
        limit=max(1, min(limit, 100)),
    )
    # Lightweight resume payload — ranker tokenizes _raw when no parsed keywords.
    return await search_jobs({"_raw": raw_resume}, filters)


@app.get("/jobs/companies")
def jobs_companies():
    """List the companies currently in the registry (for UI filter chips)."""
    return {"companies": [{"name": c.name, "slug": c.slug, "ats": c.ats}
                          for c in all_companies()]}


@app.post("/outreach/draft")
async def outreach_draft(
    request: Request,
    resume_file: UploadFile = File(None),
    resume_text: str = Form(None),
    job_title: str = Form(...),
    company: str = Form(...),
    department: str = Form(""),
    recruiter_name: str = Form(""),
    recruiter_role: str = Form(""),
    company_context: str = Form(""),   # a VERIFIED recent fact, optional
):
    """
    Draft a personalised recruiter outreach message for one job, grounded in
    the user's real resume. The LLM never fabricates — thin inputs produce an
    honest plainer message flagged with a lower confidence.
    """
    _check_rate_limit(request.client.host if request.client else "unknown")
    raw_resume = await _resolve_resume(resume_file, resume_text)

    if not job_title.strip() or not company.strip():
        raise HTTPException(400, "job_title and company are required.")

    resume_data = await parse_resume(raw_resume)
    recruiter = None
    if recruiter_name.strip():
        recruiter = {"name": recruiter_name.strip(), "role": recruiter_role.strip()}

    return await draft_outreach(
        resume_data=resume_data,
        job={"title": job_title.strip(), "company": company.strip(),
             "department": department.strip()},
        recruiter=recruiter,
        company_context=company_context.strip(),
    )


@app.get("/outreach/contacts")
def outreach_contacts(name: str = "", domain: str = ""):
    """
    Return ranked likely email addresses for a recruiter at a company domain.
    Free pattern-based guessing — these are statistically likely, not verified.
    """
    if not domain.strip():
        raise HTTPException(400, "domain is required (e.g. 'stripe.com').")
    return discover_contacts(name.strip() or None, domain.strip())


@app.get("/outreach/recruiters")
async def outreach_recruiters(company: str = "", role_hint: str = ""):
    """
    Best-effort discovery of recruiters / hiring managers at a company via free
    public search. Results need a human eye — verify before reaching out.
    """
    if not company.strip():
        raise HTTPException(400, "company is required (e.g. 'Stripe').")
    return await find_recruiters(company.strip(), role_hint.strip())


@app.post("/outreach/follow-up")
async def outreach_follow_up(
    request: Request,
    resume_file: UploadFile = File(None),
    resume_text: str = Form(None),
    job_title: str = Form(...),
    company: str = Form(...),
    original_message: str = Form(...),
    days_since: int = Form(...),
    attempt_number: int = Form(1),
    recruiter_name: str = Form(""),
):
    """Draft a follow-up to an earlier outreach that got no reply."""
    _check_rate_limit(request.client.host if request.client else "unknown")
    raw_resume = await _resolve_resume(resume_file, resume_text)
    resume_data = await parse_resume(raw_resume)
    recruiter = {"name": recruiter_name.strip()} if recruiter_name.strip() else None
    return await draft_follow_up(
        resume_data=resume_data,
        job={"title": job_title.strip(), "company": company.strip()},
        original_message=original_message,
        days_since=max(0, days_since),
        attempt_number=max(1, attempt_number),
        recruiter=recruiter,
    )


@app.post("/interview/prep")
async def interview_prep(
    request: Request,
    resume_file: UploadFile = File(None),
    resume_text: str = Form(None),
    job_description: str = Form(...),
):
    """
    Generate an interview-prep pack (likely questions + how to answer them from
    the candidate's real experience) for a specific role.
    """
    _check_rate_limit(request.client.host if request.client else "unknown")
    raw_resume = await _resolve_resume(resume_file, resume_text)

    if not job_description.strip():
        raise HTTPException(400, "Job description cannot be empty.")
    if len(job_description) > MAX_JD_CHARS:
        raise HTTPException(413, f"Job description too long (max {MAX_JD_CHARS} chars).")

    # Parse resume + JD; gap analysis sharpens the gap_questions but is optional.
    resume_data = await parse_resume(raw_resume)
    jd_data = await parse_jd(job_description)
    gap = await run_analysis(raw_resume, job_description)
    gap_result = {"missing_keywords": gap.get("missing_keywords", [])}
    return await prep_interview(resume_data, jd_data, gap_result)


@app.post("/analytics/autopsy")
def analytics_autopsy(payload: dict):
    """
    Application autopsy — funnel metrics, score correlation, and plain-language
    insights from the user's own application history.

    Body: {"applications": [ {company, match_score, tailored, outreach_sent, status}, ... ]}
    """
    applications = payload.get("applications", []) if isinstance(payload, dict) else []
    if not isinstance(applications, list):
        raise HTTPException(400, "'applications' must be a list of records.")
    return run_autopsy(applications)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
