"""
agents/resume_parser.py  —  AGENT 1
Reads raw resume text → returns structured JSON.
Model: Groq Llama-3.3-70b (free)
"""
import json, os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ════════════════════════════════════════════════════════════
#  PROMPT  — Copy-study this to understand prompt engineering
# ════════════════════════════════════════════════════════════
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

async def parse_resume(text: str) -> dict:
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.05,
            max_tokens=2500,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": f"Parse this resume:\n\n{text[:6000]}"}
            ]
        )
        raw = resp.choices[0].message.content.strip()
        raw = _clean(raw)
        return json.loads(raw)
    except Exception as e:
        print(f"[resume_parser] {e}")
        return {"skills": [], "experience_bullets": [], "all_keywords": [],
                "summary": None, "_raw": text}

def _clean(s: str) -> str:
    if "```" in s:
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    return s.strip()
