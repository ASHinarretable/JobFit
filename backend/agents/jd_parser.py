"""
agents/jd_parser.py  —  AGENT 2
Reads raw job description → extracts what the employer actually wants.
Model: Groq Llama-3.3-70b (free, configured via env)
"""
import json
import logging
import os
import re

from dotenv import load_dotenv
from groq import AsyncGroq, Groq

load_dotenv()
logger = logging.getLogger(__name__)

# ── Config constants ──────────────────────────────────────────
MODEL        = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TEMPERATURE  = float(os.getenv("JD_TEMPERATURE", "0.05"))
MAX_TOKENS   = int(os.getenv("JD_MAX_TOKENS", "2000"))
JD_MAX_CHARS = 6000   # ~1500 tokens, leaves room for prompt + response

# ── Default structure — returned when parsing fails ───────────
DEFAULT = {
    "job_title":             None,
    "company":               None,
    "seniority":             "not specified",
    "employment_type":       "not specified",
    "required_skills":       [],
    "preferred_skills":      [],
    "technologies":          [],
    "soft_skills":           [],
    "experience_required":   "not specified",
    "education_required":    "not specified",
    "keywords":              [],
    "keyword_frequency":     {},
    "must_have_phrases":     [],
    "red_flags_if_missing":  [],
    "responsibilities":      [],
    "industry_context":      None,
}

SYSTEM = """
You are a senior technical recruiter with 15 years of experience parsing job descriptions.

Your job: extract EXACTLY what the employer wants so a candidate can tailor their resume.

Return ONLY a valid JSON object — no markdown, no explanation:

{
  "job_title": "exact role title",
  "company": "company name or null",
  "seniority": "intern | fresher | junior | mid | senior | lead",
  "employment_type": "full-time | internship | contract | part-time",
  "required_skills": ["skills explicitly labeled required / must-have"],
  "preferred_skills": ["skills labeled preferred / nice-to-have / bonus"],
  "technologies": ["every specific tool, language, framework, cloud, platform"],
  "soft_skills": ["communication", "teamwork",etc.],
  "experience_required": "e.g. 0-1 years / 2+ years / fresher / not specified",
  "education_required": "e.g. B.Tech CS / Any degree / not specified",
  "keywords": ["COMPREHENSIVE list — every technical term an ATS would scan for.  Include synonyms: e.g. both 'REST' and 'REST API' and 'RESTful'"],
  "keyword_frequency": { "Python": 4, "Docker": 2 },
  "must_have_phrases": ["exact phrases from the JD that should appear on a resume"],
  "red_flags_if_missing": ["3-5 skills so critical missing them = instant rejection"],
  "responsibilities": ["key responsibilities listed in the JD"],
  "industry_context": "one sentence about what this role/company does"
}

Rules:
- Return ONLY the JSON object, nothing else.
- keywords must be exhaustive — this is what gets compared against the resume.
- red_flags_if_missing: only truly non-negotiable skills.
"""
_client = None  # Lazy init on first use

# ── Lazy client init ──────────────────────────────────────────
def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not found. Check your .env file.")
    _client = AsyncGroq(api_key=api_key)
    return _client


# ── JSON cleaner ──────────────────────────────────────────────
def _extract_json_from_llm_output(s: str) -> str:
    if not s:
        return ""
    """Strip markdown fences and extract the first valid JSON object."""
    if "```" in s:
        parts = s.split("```")
        for part in parts:
            if "{" in part and "}" in part:
                s = part
                break

    # No fences — extract first { ... } block directly
    match = re.search(r'\{.*\}', s, re.DOTALL)
    return match.group() if match else s.strip()

    return s.strip()


# ── Shape validator ───────────────────────────────────────────
def _validate(data: dict) -> dict:
    """Merge parsed data into defaults so all keys always exist."""
    validated = {**DEFAULT, **data}
    
    #ensure lists
    for key in ["required_skills", "preferred_skills", "technologies", "soft_skills", "keywords", "must_have_phrases", "red_flags_if_missing", "responsibilities"]:
        if not isinstance(validated[key], list):
            validated[key] = []
            
    #ensure dict
    if not isinstance(validated["keyword_frequency"], dict):
        validated["keyword_frequency"] = {}
                
    return validated


# ── Main function ─────────────────────────────────────────────
async def parse_jd(text: str) -> dict:
    """
    Parse a job description and extract structured requirements.

    Args:
        text: Raw job description text

    Returns:
        dict with keys: job_title, required_skills, preferred_skills,
        technologies, keywords, red_flags_if_missing, and more.
        Always returns a complete dict — missing fields use defaults.
    """
    try:
        client = _get_client()
        truncated_text = text[:JD_MAX_CHARS]
        resp = await client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": f"Parse this job description:\n\n{truncated_text}"}
            ]
        )

        raw = resp.choices[0].message.content.strip()
        raw = _extract_json_from_llm_output(raw)
        parsed = json.loads(raw)
        return _validate(parsed)

    except json.JSONDecodeError as e:
        logger.error(f"[jd_parser] JSON parse failed: {e}")
        logger.debug(f"[jd_parser] Raw output: {raw[:500]}")
        return _validate({})

    except Exception as e:
        logger.error(f"[jd_parser] Unexpected error: {e}")
        return _validate({})


# ── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    test_jd = """
    Backend Developer — FinTech Startup, Mumbai
    We are hiring a Python developer to build financial data APIs.
    Must have: Python, Django, REST APIs, PostgreSQL
    Nice to have: Docker, AWS, Redis
    Experience: 1-3 years. B.Tech CS preferred.
    Responsibilities:
    - Design and build RESTful APIs for mobile and web clients
    - Write and optimise PostgreSQL queries
    - Collaborate with frontend team in an Agile environment
    """

    result = parse_jd(test_jd)
    print(json.dumps(result, indent=2))