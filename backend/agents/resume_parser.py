"""
agents/resume_parser.py  —  AGENT 1
Reads raw resume text → returns structured JSON.
Model: Groq Llama-3.3-70b (free)
"""
import json, os, asyncio, logging, re
from groq import AsyncGroq
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import random
import time
import hashlib
load_dotenv()
logger = logging.getLogger(__name__)
MAX_RETRIES = 3
MAX_CHARS = 6000
BASE_DELAY = 1

_client = None
class ResumeResponse(BaseModel):
  name : Optional[str]
  contact: Dict[str, Optional[str]] = Field(default_factory=dict)
  format_flags: Dict = Field(default_factory=dict)
  summary: Optional[str]
  skills: List[str] = Field(default_factory=list)
  experience: List[dict] = Field(default_factory=list)
  education: List[dict] = Field(default_factory=list)
  certifications: List[dict] = Field(default_factory=list)
  projects: List[dict] = Field(default_factory=list)
  experience_bullets: List[str] = Field(default_factory=list)
  all_keywords: List[str] = Field(default_factory=list)
  
# ════════════════════════════════════════════════════════════
#  PROMPT  — Copy-study this to understand prompt engineering
# ══════════════════════════════════════════
SYSTEM = """
You are a precise resume parser specialising in ATS (Applicant Tracking Systems).

Parse the resume and return ONLY a valid JSON object — no markdown fences, no explanation,
no text before or after. The JSON must have exactly this shape:

{
  "name": "string or null",
  "contact": {
    "email": "string or null",
    "phone": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "location": "city/state string or null"
  },
  "summary": "full text of summary/profile section or null",
  "skills": ["every technical skill, tool, language, framework mentioned"],
  "experience": [
    {
      "title": "job title",
      "company": "company name",
      "duration": "date range",
      "bullets": ["bullet 1", "bullet 2"]
    }
  ],
  "education": [
    {
      "degree": "degree name",
      "institution": "college name",
      "year": "graduation year",
      "cgpa": "CGPA or percentage if present else null"
    }
  ],
  "certifications": ["cert 1", "cert 2"],
  "projects": [
    {
      "name": "project name",
      "description": "what it does",
      "technologies": ["tech1", "tech2"]
    }
  ],
  "experience_bullets": ["flat list of every bullet point from every job"],
  "all_keywords": [
    "COMPREHENSIVE list of every technical term, tool, language, framework,
     methodology, domain, certification, and soft skill in the resume"
  ],
  "format_flags": {
    "has_tables":              false,
    "has_columns":             false,
    "uses_standard_headings":  true,
    "has_profile_summary":     true,
    "total_pages_estimated":   1
  }
}

Rules:
- Return ONLY the JSON object, nothing else.
- all_keywords must be exhaustive — this powers the match score.
- experience_bullets = every bullet verbatim (used for rewriting).
- If a field is missing, use null or [].
- Do NOT hallucinate data not present in the resume.
"""

def _get_client():
    global _client
    if _client is None:
      api_key = os.getenv("GROQ_API_KEY")
      if not api_key:
        raise ValueError ("GROQ_API_KEY is missing")  
      _client = AsyncGroq(api_key=api_key) 
    return _client

def _extract_json(s: str) -> str:
    if not s:
        return ""

    if "```" in s:
        parts = s.split("```")
        for part in parts:
            if "{" in part and "}" in part:
                s = part
                break

    # Find first valid JSON block (balanced braces)
    start = s.find("{")
    end = s.rfind("}")
    
    if start != -1 and end != -1:
        return s[start:end+1]

    return s.strip()   

def _validate(data: dict, raw_text: str) -> dict: 
    default = {
      "name": None,
      "contact": {
        "email": None,
        "phone": None, 
        "linkedin": None,
        "github": None,
        "location": None
      },
      "summary": None,
      "skills": [],
      "experience": [],
      "education": [],
      "certifications": [],
      "projects": [],
      "experience_bullets": [],
      "all_keywords": [],
      "format_flags": {
        "has_tables": False,
        "has_columns": False,
        "uses_standard_headings": True,
        "has_profile_summary": False,
        "total_pages_estimated": 1
      },
      "_raw": raw_text
    }
    
    validated = {**default, **data}
    
    #ensure lists
    for key in ["skills", "experience", "education", "certifications", "projects", "experience_bullets", "all_keywords"]:
      if not isinstance(validated.get(key), list):
        validated[key] = []
        
    #deduplicate 
    validated["all_keywords"] = _normalize_keywords(validated["all_keywords"])
     # deduplicate while preserving order 
    validated["_confidence"] = {
    "has_skills": bool(validated["skills"]),
    "has_experience": bool(validated["experience"]),
    "has_projects": bool(validated["projects"]),
    }
    validated["_confidence_score"] = sum([
    validated["_confidence"]["has_skills"],
    validated["_confidence"]["has_experience"],
    validated["_confidence"]["has_projects"]
    ]) / 3
    
    validated["_keyword_count"] = len(validated["all_keywords"])
    return validated

def _smart_truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    
    # Keep start + end (important sections often at both)
    return text[:limit//2] + "\n...\n" + text[-limit//2:]
  
def _normalize_keywords(keywords: List[str]) -> List[str]:
    return list(dict.fromkeys([
        k.lower().replace("-", " ").strip()
        for k in keywords
        if isinstance(k, str) and k.strip()
    ]))
    
def _hash_text(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]
      
async def parse_resume(text: str) -> dict:
    client = _get_client()
    truncated_text = _smart_truncate(text, MAX_CHARS)

    start_time = time.time()   # latency tracking
    request_id = _hash_text(text)  # unique trace ID

    for attempt in range(MAX_RETRIES):
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    temperature=0.05,
                    max_tokens=2500,
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"Parse this resume:\n\n{truncated_text}"}
                    ]
                ),
                timeout=20
            )

            raw = resp.choices[0].message.content.strip()
            raw = _extract_json(raw)
            parsed = json.loads(raw)

            # Pydantic validation
            validated = ResumeResponse(**parsed)

            # Stronger semantic validation
            if len(validated.all_keywords) < 5:
                raise ValueError("Too few keywords extracted")

            result = _validate(validated.model_dump(), text)

            # metadata block
            result["_meta"] = {
                "parser_version": "v1",
                "attempts": attempt + 1,
                "request_id": request_id,
                "latency_ms": int((time.time() - start_time) * 1000)
            }

            return result

        except Exception as e:
            err = str(e).lower()

            logger.warning(
                "[resume_parser] attempt=%d error=%s raw_snippet=%s",
                attempt + 1,
                str(e),
                raw[:200] if 'raw' in locals() else "N/A"
            )

            # ✅ reason-based retry
            if attempt < MAX_RETRIES - 1:
                if "rate limit" in err:
                    await asyncio.sleep(BASE_DELAY * (2 ** attempt) + random.uniform(1, 2))
                elif "timeout" in err:
                    await asyncio.sleep(1)
                elif "invalid" in err or "api key" in err:
                    raise e  # don't retry
                else:
                    await asyncio.sleep(BASE_DELAY * (2 ** attempt))

    # All retries failed
    logger.error("[resume_parser] All attempts failed.")

    result = _validate({}, text)

    result["_meta"] = {
        "parser_version": "v1",
        "attempts": MAX_RETRIES,
        "status": "failed",
        "request_id": request_id,
        "latency_ms": int((time.time() - start_time) * 1000)
    }

    return result