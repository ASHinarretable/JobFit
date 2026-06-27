"""
agents/gap_analyzer.py  —  AGENT 3
Compares resume vs JD → match score, gaps, quick wins.
Model: Groq Llama-3.3-70b (free)
"""
import json, os, asyncio, random
from dotenv import load_dotenv
import logging
from pydantic import BaseModel, Field
from typing import List, Dict
import hashlib
from utils.json_utils import extract_json
from utils.llm_client import get_client
load_dotenv()
logger = logging.getLogger(__name__)
_cache = {}

class SectionScores(BaseModel):
    skills_match: int = 0
    experience_match: int = 0
    education_match: int = 0
    keywords_match: int = 0
    format_score: int = 0

class GapResponse(BaseModel):
    overall_score: int = 0
    section_scores: SectionScores = Field(default_factory=SectionScores)
    missing_keywords: List[Dict] = Field(default_factory=list)
    present_keywords: List[str] = Field(default_factory=list)
    format_issues: List[str] = Field(default_factory=list)
    quick_wins: List[Dict] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    honest_assessment: str = ""
    score_to_reach_75_percent: List[str] = Field(default_factory=list)
 
#constants
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TEMPERATURE = float(os.getenv("GAP_TEMPERATURE", "0.15"))
MAX_TOKENS = int(os.getenv("GAP_MAX_TOKENS", "2800"))
MAX_RETRIES = 3
BASE_DELAY = 1
CACHE_MAX_SIZE = 500   # bound the in-memory cache
          
# ════════════════════════════════════════════════════════════
#  PROMPT  — The most important prompt in the whole app
# ════════════════════════════════════════════════════════════
SYSTEM = """
You are an ATS expert and brutally honest career coach.

You receive structured data from a candidate's resume and a job description.
Your job: produce a precise, honest gap analysis.

Return ONLY a valid JSON object — no markdown, no explanation:

{
  "overall_score": 68,

  "section_scores": {
    "skills_match":     75,
    "experience_match": 60,
    "education_match":  90,
    "keywords_match":   55,
    "format_score":     80
  },

  "missing_keywords": [
    {
      "keyword":             "Docker",
      "importance":          "critical",
      "frequency_in_jd":     3,
      "suggested_placement": "Skills section and DevOps project description",
      "context":             "JD mentions Docker for containerising microservices"
    }
  ],

  "present_keywords": ["Python", "REST API", "Git"],

  "format_issues": [
    "Resume appears to use multi-column layout — ATS often reads columns out of order",
    "Section heading 'My Work' should be renamed to 'Work Experience' for ATS"
  ],

  "quick_wins": [
    {
      "action":  "Add 'REST API' to your Skills section",
      "impact":  "+7 points",
      "effort":  "30 seconds"
    },
    {
      "action":  "Add 'Agile / Scrum' to your Skills or most recent job",
      "impact":  "+5 points",
      "effort":  "1 minute"
    },
    {
      "action":  "Rename 'About Me' section to 'Professional Summary'",
      "impact":  "+3 points",
      "effort":  "10 seconds"
    }
  ],

  "strengths": [
    "Python skills strongly demonstrated across projects and experience",
    "Education matches what the JD requires exactly"
  ],

  "honest_assessment": "2–3 sentences, direct mentor tone. Name the biggest gap. Be specific.",

  "score_to_reach_75_percent": [
    "Add Docker to skills if you have used it even briefly",
    "Include 'REST API development' phrase in at least one bullet point",
    "Add a short Professional Summary at the top"
  ]
}

Scoring rules:
- overall_score must be honest. Do NOT inflate.
- 85–100 = excellent match, very likely to pass ATS
- 70–84  = good match, some gaps to fix
- 55–69  = partial match, meaningful gaps
- <55    = significant mismatch
- skills_match    = (JD required_skills found in resume skills) / total required × 100
- keywords_match  = (JD keywords found in resume all_keywords) / total JD keywords × 100
- experience_match = subjective: does the resume experience level match JD seniority?
- education_match  = does resume education meet JD education requirement?
- format_score     = ATS friendliness based on format_flags
- missing_keywords: mark "critical" if frequency ≥ 2 OR it's in red_flags_if_missing
- quick_wins: only the top 3, ranked by impact/effort ratio, each doable in <5 min
- honest_assessment: speak like a mentor, name specifics, don't pad
"""

def _make_cache_key(resume: dict, jd: dict) -> str:
    raw = json.dumps({"r": resume, "j": jd}, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()
  
def _fallback_analysis(resume, jd):
    resume_keywords = set(map(str.lower, resume.get("all_keywords", [])))
    jd_keywords = set(map(str.lower, jd.get("keywords", [])))

    matched = resume_keywords & jd_keywords
    score = int((len(matched) / (len(jd_keywords) or 1)) * 100)

    return {
        "overall_score": score,
        "section_scores": {
          "skills_match": 0,
          "experience_match": 0,
          "education_match": 0,
          "keywords_match": score,
          "format_score": 0
          },
        "missing_keywords": list(jd_keywords - resume_keywords),
        "present_keywords": list(matched),
        "format_issues": [],
        "quick_wins": [],
        "strengths": [],
        "honest_assessment": "Fallback analysis used due to LLM failure.",
        "score_to_reach_75_percent": []
    }

async def analyze_gaps(resume: dict, jd: dict) -> dict:
    client = get_client()
    cache_key = _make_cache_key(resume, jd)

    if cache_key in _cache:
        logger.info("[gap_analyzer] cache hit")
        return _cache[cache_key]
    
    # Trim payload to save tokens
    r = {
        "skills":       resume.get("skills", []),
        "all_keywords": resume.get("all_keywords", []),
        "bullets_sample": resume.get("experience_bullets", [])[:6],
        "education":    resume.get("education", []),
        "has_summary":  bool(resume.get("summary")),
        "format_flags": resume.get("format_flags", {}),
    }
    j = {
        "required_skills":       jd.get("required_skills", []),
        "preferred_skills":      jd.get("preferred_skills", []),
        "technologies":          jd.get("technologies", []),
        "keywords":              jd.get("keywords", [])[:40],
        "red_flags_if_missing":  jd.get("red_flags_if_missing", []),
        "experience_required":   jd.get("experience_required", ""),
        "education_required":    jd.get("education_required", ""),
        "seniority":             jd.get("seniority", ""),
        "must_have_phrases":     jd.get("must_have_phrases", []),
    }

    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content":
                        f"RESUME DATA:\n{json.dumps(r)}\n\n"
                        f"JD DATA:\n{json.dumps(j)}\n\n"
                        "Produce the gap analysis JSON."}
                ],
                timeout=20
            )

            raw = resp.choices[0].message.content.strip()
            parsed = extract_json(raw)

            # Schema validation
            validated = GapResponse(**parsed)

            result = validated.model_dump()

            #Safety clamp
            result["overall_score"] = max(0, min(100, int(result.get("overall_score", 0))))

            #Meta info
            result["_meta"] = {
                "attempts": attempt + 1,
                "parser": "gap_analyzer_v2"
            }

            # Cache successful results only (bounded to avoid unbounded growth)
            if len(_cache) < CACHE_MAX_SIZE:
                _cache[cache_key] = result

            return result
        except json.JSONDecodeError:
          logger.warning("[gap_analyzer] JSON parse failed")

        except asyncio.TimeoutError:
            logger.warning("[gap_analyzer] Timeout")
            
        except Exception as e:
            logger.warning("[gap_analyzer] attempt=%d error=%s", attempt+1, str(e))

        # Backoff retry
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(BASE_DELAY * (2 ** attempt) + random.uniform(0, 1))        

    #Fallback (ONLY after all retries fail)
    logger.error("[gap_analyzer] All attempts failed — using fallback")

    result = _fallback_analysis(resume, jd)
    result["_meta"] = {
        "attempts": MAX_RETRIES,
        "parser": "gap_analyzer_v2",
        "status": "fallback_used"
    }
    # Do NOT cache fallback results — the LLM may recover on the next request.
    return result
