"""
ResumeRadar — FastAPI Backend
Entry point. Runs the 4-agent analysis via the LangGraph pipeline.
"""
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from agents.graph import run_analysis
from utils.pdf_extractor import extract_text
import uvicorn, os, time
from collections import deque

app = FastAPI(title="ResumeRadar API", version="1.0.0")

# Comma-separated list of allowed origins, e.g.
#   ALLOWED_ORIGINS=https://resumeradar.vercel.app,http://localhost:5173
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
    return {"status": "ok", "app": "ResumeRadar", "version": "1.0.0"}

@app.get("/health")
def health():
    # Koyeb uses this for health checks
    return {"status": "healthy"}

@app.post("/analyze")
async def analyze(
    request: Request,
    resume_file: UploadFile = File(None),
    resume_text: str = Form(None),
    job_description: str = Form(...)
):
    _check_rate_limit(request.client.host if request.client else "unknown")

    # ── Extract resume text ──────────────────────────────────
    if resume_file and resume_file.filename:
        file_bytes = await resume_file.read()
        if len(file_bytes) > MAX_FILE_BYTES:
            raise HTTPException(413, f"File too large (max {MAX_FILE_BYTES // (1024*1024)} MB).")
        raw_resume = extract_text(file_bytes, resume_file.filename)
    elif resume_text and resume_text.strip():
        raw_resume = resume_text.strip()[:MAX_RESUME_CHARS]
    else:
        raise HTTPException(400, "Provide a resume file or paste resume text.")

    if not raw_resume.strip():
        raise HTTPException(400, "Could not read any text from the resume.")

    if not job_description.strip():
        raise HTTPException(400, "Job description cannot be empty.")
    if len(job_description) > MAX_JD_CHARS:
        raise HTTPException(413, f"Job description too long (max {MAX_JD_CHARS} chars).")

    # ── Run the 4-agent LangGraph pipeline ──────────────────
    return await run_analysis(raw_resume, job_description)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
