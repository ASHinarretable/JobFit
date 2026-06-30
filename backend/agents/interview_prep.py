"""
agents/interview_prep.py  —  AGENT 6
Generates a focused interview-prep pack for a specific role, grounded in the
candidate's real resume and the actual job description.

Why it belongs in JobFit: outreach gets the reply, the reply leads to an
interview — and right then the user needs exactly this. It's the natural next
node after a recruiter responds, and no competitor connects the funnel this far.

The valuable, hard part is the GAP questions: the interviewer will probe where
the resume is thin against the JD. Surfacing those in advance — with an honest
way to handle each — is what turns this from a generic question list into prep.

Model: Groq Llama-3.3-70b (free) primary, Gemini Flash fallback.
"""
import json
import logging
import os
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from utils.json_utils import extract_json
from utils.llm_client import get_client
from utils.retry import retry_async

load_dotenv()
logger = logging.getLogger(__name__)

MODEL       = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TEMPERATURE = float(os.getenv("INTERVIEW_TEMPERATURE", "0.4"))
MAX_TOKENS  = int(os.getenv("INTERVIEW_MAX_TOKENS", "2200"))


class _QA(BaseModel):
    question: str = ""
    why_asked: str = ""
    your_angle: str = ""        # talking points drawn from the candidate's REAL experience


class InterviewResponse(BaseModel):
    technical_questions: List[_QA] = Field(default_factory=list)
    behavioral_questions: List[_QA] = Field(default_factory=list)
    gap_questions: List[_QA] = Field(default_factory=list)
    questions_to_ask_them: List[str] = Field(default_factory=list)
    prep_summary: str = ""


DEFAULT = {
    "technical_questions": [],
    "behavioral_questions": [],
    "gap_questions": [],
    "questions_to_ask_them": [],
    "prep_summary": "",
}

# ════════════════════════════════════════════════════════════
#  PROMPT
# ════════════════════════════════════════════════════════════
SYSTEM = """
You are a senior engineering interviewer and career coach. You prepare a
candidate for a SPECIFIC role by predicting the questions they'll actually face
and arming them with answers built from their REAL background.

You receive a JSON object with the candidate's resume summary, skills, and
achievements; the job's title, company, and key requirements; and the specific
keyword gaps between them (skills the JD wants that the resume lacks).

Return ONLY a valid JSON object:

{
  "technical_questions": [
    {
      "question": "a realistic technical question this role would ask",
      "why_asked": "what the interviewer is really testing",
      "your_angle": "specific talking points from the candidate's OWN projects/experience to answer well"
    }
  ],
  "behavioral_questions": [
    {
      "question": "a realistic behavioural/STAR question",
      "why_asked": "the trait being assessed",
      "your_angle": "which real experience of theirs to tell as the story"
    }
  ],
  "gap_questions": [
    {
      "question": "a question that probes a SKILL GAP between resume and JD",
      "why_asked": "why this gap will come up",
      "your_angle": "an honest way to handle it — bridge from adjacent experience, show learning ability; NEVER fake competence"
    }
  ],
  "questions_to_ask_them": [
    "3-5 sharp questions the candidate should ask the interviewer — specific to this role/company, signalling genuine interest, never generic"
  ],
  "prep_summary": "3-4 sentences: where this candidate is strong for this role, where they're exposed, and the single thing to rehearse most."
}

RULES:
- Generate 4-6 technical, 3-4 behavioural, and 2-4 gap questions.
- your_angle must reference the candidate's REAL achievements — never invent experience.
- For gap_questions: be honest. The right move is bridging from adjacent skills
  and showing how they'd ramp — not pretending they already know it.
- Tailor difficulty to the role's seniority.
- Return ONLY the JSON object, nothing else.
"""


def _brief(resume_data: dict, jd_data: dict, gap_result: dict) -> dict:
    """Compact the inputs to just what the model needs to predict questions."""
    return {
        "candidate": {
            "summary": resume_data.get("summary"),
            "skills": (resume_data.get("skills") or resume_data.get("all_keywords") or [])[:15],
            "achievements": (resume_data.get("experience_bullets") or [])[:8],
        },
        "job": {
            "title": jd_data.get("job_title") or jd_data.get("title"),
            "company": jd_data.get("company"),
            "seniority": jd_data.get("seniority", "not_specified"),
            "required_skills": (jd_data.get("required_skills") or [])[:12],
            "responsibilities": (jd_data.get("responsibilities") or [])[:8],
        },
        # The gap is the gold — these become the gap_questions.
        "skill_gaps": _gap_keywords(gap_result, jd_data),
    }


def _gap_keywords(gap_result: dict, jd_data: dict) -> List[str]:
    """Pull the missing-skill list from gap analysis, falling back to JD red flags."""
    missing = gap_result.get("missing_keywords") if gap_result else None
    if missing:
        # missing_keywords may be strings or {keyword: ...} dicts
        return [m if isinstance(m, str) else m.get("keyword", "") for m in missing][:10]
    return (jd_data.get("red_flags_if_missing") or [])[:10]


async def prep_interview(resume_data: dict, jd_data: dict, gap_result: dict | None = None) -> dict:
    """
    Build the interview-prep pack. Always returns a complete dict; never raises.
    gap_result is optional but strongly improves the gap_questions.
    """
    payload = _brief(resume_data, jd_data, gap_result or {})
    user_message = f"Prepare interview questions for:\n\n{json.dumps(payload, indent=2, ensure_ascii=False)}"

    async def call_groq() -> dict:
        client = get_client()
        resp = await client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_message},
            ],
        )
        return extract_json(resp.choices[0].message.content)

    async def call_gemini() -> dict:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=SYSTEM)
        resp = model.generate_content(user_message)
        return extract_json(resp.text)

    try:
        raw = await retry_async(call_groq, retries=3)
    except Exception as groq_error:
        logger.warning("[interview_prep] Groq failed: %s — trying Gemini", groq_error)
        try:
            raw = await retry_async(call_gemini, retries=2)
        except Exception as gemini_error:
            logger.error("[interview_prep] Both providers failed: %s", gemini_error)
            return {**DEFAULT, "prep_summary": "Could not generate prep right now. Please try again."}

    try:
        return InterviewResponse(**raw).model_dump()
    except Exception as e:
        logger.warning("[interview_prep] schema validation failed: %s", e)
        return {**DEFAULT, **{k: raw.get(k) for k in DEFAULT if k in raw}}


# ── Smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    resume = {
        "summary": "Backend developer, Python APIs and data systems.",
        "skills": ["Python", "Django", "REST APIs", "PostgreSQL", "Git"],
        "experience_bullets": [
            "Built Django REST APIs serving 50k daily requests",
            "Cut PostgreSQL query latency 30% with composite indexes",
        ],
    }
    jd = {
        "job_title": "Backend Engineer", "company": "Stripe", "seniority": "mid",
        "required_skills": ["Python", "Go", "Kubernetes", "distributed systems", "AWS"],
        "responsibilities": ["Build payment APIs", "Own service reliability"],
    }
    gap = {"missing_keywords": ["Go", "Kubernetes", "distributed systems", "AWS"]}
    out = asyncio.run(prep_interview(resume, jd, gap))
    print(json.dumps(out, indent=2))
