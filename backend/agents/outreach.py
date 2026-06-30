"""
agents/outreach.py  —  AGENT 5
Drafts a short, personalised outreach message to a recruiter / hiring manager
for a specific job, grounded in the candidate's real resume.

Why this exists (the competitive moat):
No other tool in the space — not LinkedIn, not Jobscan, not Teal — drafts a
personalised recruiter message that references the role, the recruiter's
background, and a recent company fact. Personalised outreach gets ~71% more
replies than templated spray (LinkedIn data). This agent is that workflow.

Model: Groq Llama-3.3-70b (free) primary, Gemini Flash fallback — same as the
rest of the pipeline.

The cardinal rule: NEVER fabricate. The message may only reference facts that
were passed in (the candidate's real achievements, the real job, any verified
company context). A made-up "I loved your recent post about X" is worse than
no personalisation at all — it gets the candidate caught.
"""
import json
import logging
import os
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from utils.json_utils import extract_json
from utils.llm_client import get_client
from utils.retry import retry_async

load_dotenv()
logger = logging.getLogger(__name__)

MODEL       = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TEMPERATURE = float(os.getenv("OUTREACH_TEMPERATURE", "0.6"))  # warmer — this is creative writing
MAX_TOKENS  = int(os.getenv("OUTREACH_MAX_TOKENS", "900"))


# ── Output schema ─────────────────────────────────────────────
class OutreachResponse(BaseModel):
    subject: str = ""
    body: str = ""
    personalization_used: List[str] = Field(default_factory=list)
    follow_up: str = ""
    confidence: str = "medium"          # high | medium | low
    warnings: List[str] = Field(default_factory=list)


DEFAULT = {
    "subject": "",
    "body": "",
    "personalization_used": [],
    "follow_up": "",
    "confidence": "low",
    "warnings": [],
}

# ════════════════════════════════════════════════════════════
#  PROMPT
# ════════════════════════════════════════════════════════════
SYSTEM = """
You are an expert at writing cold outreach messages that get replies from busy
recruiters and hiring managers. You write the way a thoughtful, confident
candidate would — never like a marketer, never like a template.

You will receive a JSON object describing a candidate, a job, optionally the
recruiter, and optionally a VERIFIED recent fact about the company.

Write a short outreach message and return ONLY a valid JSON object:

{
  "subject": "A specific, non-generic subject line (under 8 words). Reference the role.",
  "body": "The message body. STRICT RULES BELOW.",
  "personalization_used": ["list each concrete, specific detail you referenced"],
  "follow_up": "ONE sentence to send 5 days later if there's no reply. Polite, short, adds a new angle — never just 'bumping this'.",
  "confidence": "high | medium | low — how strong this message is given the inputs you had",
  "warnings": ["anything the user should know before sending — e.g. 'no company context provided, message is necessarily more generic'"]
}

BODY RULES (non-negotiable):
1. 4 sentences MAXIMUM. Recruiters skim. Long = unread.
2. Sentence 1: who you are + the role you're interested in (specific title).
3. Sentence 2: your single strongest, most relevant proof point — pulled from
   the candidate's REAL achievements. Quantified if the data allows.
4. Sentence 3: one specific, genuine reason this company/role — use the VERIFIED
   company fact if one was provided; otherwise tie to the role itself. Never invent.
5. Sentence 4: a low-friction ask ("Open to a quick chat?" / "Worth a brief call?").
6. Warm-professional tone. No "I hope this email finds you well." No buzzwords
   ("synergy", "passionate", "rockstar", "leverage"). No flattery that isn't earned.
7. Address the recruiter by first name ONLY if a name was provided. Otherwise
   open with "Hi there," — never "Dear Hiring Manager" or "To whom it may concern".

ABSOLUTE RULE — NEVER FABRICATE:
- Do not invent achievements, metrics, posts, news, or shared connections.
- Only reference facts present in the input. If you have little to work with,
  write an honest, plainer message and set confidence to "low" — a generic-but-
  true message beats a personalised-but-fake one every time.
- Every item in personalization_used must trace to a real input field.

Return ONLY the JSON object, nothing else.
"""


# ── Input assembly ────────────────────────────────────────────
def _build_user_message(payload: dict) -> str:
    """Shape the structured inputs into the prompt the model sees."""
    return f"Write the outreach message for:\n\n{json.dumps(payload, indent=2, ensure_ascii=False)}"


def _candidate_brief(resume_data: dict) -> dict:
    """
    Distil the (large) parsed resume down to just what the drafter needs.
    Keeps the prompt small and steers the model toward the best proof points.
    """
    bullets = resume_data.get("experience_bullets", []) or []
    skills = resume_data.get("skills", []) or resume_data.get("all_keywords", []) or []
    return {
        "name": resume_data.get("name"),
        "headline_summary": resume_data.get("summary"),
        "top_skills": skills[:12],
        # The achievement bullets are the raw material for the proof-point sentence.
        "achievements": bullets[:6],
    }


# ── Main entry point ──────────────────────────────────────────
async def draft_outreach(
    resume_data: dict,
    job: dict,
    recruiter: Optional[dict] = None,
    company_context: str = "",
) -> dict:
    """
    Draft a personalised outreach message.

    Args:
        resume_data: parsed resume (output of resume_parser.parse_resume)
        job:         dict with at least {title, company}; description optional
        recruiter:   optional {name, role} of the person being contacted
        company_context: optional VERIFIED recent fact about the company
                         (e.g. "just raised a Series B", "launched X last month").
                         Must be true — it goes straight into the message.

    Returns:
        dict matching OutreachResponse — always complete, never raises.
    """
    payload = {
        "candidate": _candidate_brief(resume_data),
        "job": {
            "title": job.get("title") or job.get("job_title"),
            "company": job.get("company"),
            "department": job.get("department", ""),
        },
        "recruiter": recruiter or None,
        "verified_company_context": company_context or None,
    }
    user_message = _build_user_message(payload)

    # Warn upfront about thin inputs so the user calibrates trust in the draft.
    pre_warnings: List[str] = []
    if not company_context:
        pre_warnings.append(
            "No verified company context provided — message ties to the role only. "
            "Add a recent, true company fact for a stronger draft."
        )
    if not (recruiter and recruiter.get("name")):
        pre_warnings.append(
            "No recruiter name — message opens generically. Find the hiring "
            "manager's name to lift reply rates."
        )

    # ───────── GROQ (primary) ─────────
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

    # ───────── GEMINI (fallback) ─────────
    async def call_gemini() -> dict:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM,
        )
        resp = model.generate_content(user_message)
        return extract_json(resp.text)

    raw: dict = {}
    try:
        raw = await retry_async(call_groq, retries=3)
    except Exception as groq_error:
        logger.warning("[outreach] Groq failed: %s — trying Gemini", groq_error)
        try:
            raw = await retry_async(call_gemini, retries=2)
        except Exception as gemini_error:
            logger.error("[outreach] Both providers failed: %s", gemini_error)
            result = {**DEFAULT}
            result["warnings"] = pre_warnings + [
                "Could not generate a draft right now. Please try again."
            ]
            return result

    # Validate / coerce shape, then merge in the pre-flight warnings.
    try:
        validated = OutreachResponse(**raw).model_dump()
    except Exception as e:
        logger.warning("[outreach] schema validation failed: %s", e)
        validated = {**DEFAULT, **{k: raw.get(k) for k in DEFAULT if k in raw}}

    validated["warnings"] = pre_warnings + list(validated.get("warnings", []))
    if not validated.get("body"):
        validated["confidence"] = "low"
        validated["warnings"].append("Draft came back empty — try regenerating.")
    return validated


# ════════════════════════════════════════════════════════════
#  SMART FOLLOW-UP
# ════════════════════════════════════════════════════════════
# Most outreach value is lost because people never follow up — or they send a
# limp "just bumping this." A good follow-up adds a NEW angle each time and
# knows when to stop (after 2 attempts, more is pestering).
MAX_FOLLOW_UPS = int(os.getenv("MAX_FOLLOW_UPS", "2"))


class FollowUpResponse(BaseModel):
    subject: str = ""
    body: str = ""
    new_angle: str = ""          # the fresh hook this follow-up adds
    should_send: bool = True
    confidence: str = "medium"
    warnings: List[str] = Field(default_factory=list)


FOLLOW_SYSTEM = """
You write brief, high-class follow-up messages to recruiters who haven't replied
to a candidate's earlier outreach. The whole point of a follow-up is to add a
NEW reason to engage — never to just say "bumping this" or "checking in".

You receive the original message, the job, the candidate's real achievements,
how many days have passed, and which follow-up attempt this is.

Return ONLY a valid JSON object:

{
  "subject": "short subject — ideally 'Re:' the original thread feel",
  "body": "2-3 sentences MAX. Reference the role briefly, add ONE genuinely new angle (a different relevant achievement, a recent thought on the role, a small piece of value), then a soft ask. Warm, never needy.",
  "new_angle": "one phrase naming the new hook you used",
  "should_send": true,
  "confidence": "high | medium | low",
  "warnings": ["any caveats"]
}

RULES:
- NEVER fabricate. The new angle must come from the candidate's real input.
- Keep it shorter than the original. Brevity signals respect for their time.
- No guilt-tripping, no "I haven't heard back", no desperation.
- Return ONLY the JSON object.
"""


async def draft_follow_up(
    resume_data: dict,
    job: dict,
    original_message: str,
    days_since: int,
    attempt_number: int = 1,
    recruiter: Optional[dict] = None,
) -> dict:
    """
    Draft a follow-up to an earlier outreach that got no reply.

    Args:
        original_message: the body of the message already sent
        days_since:       days elapsed since that message
        attempt_number:   1 for the first follow-up, 2 for the second, etc.

    Returns FollowUpResponse-shaped dict. If attempt_number exceeds the cap,
    returns should_send=False with guidance instead of another nudge.
    """
    if attempt_number > MAX_FOLLOW_UPS:
        return {
            "subject": "", "body": "", "new_angle": "",
            "should_send": False,
            "confidence": "high",
            "warnings": [
                f"You've already followed up {MAX_FOLLOW_UPS} times. Further messages "
                "risk annoying the recruiter — better to move on to other roles or "
                "reach a different person at the company."
            ],
        }

    payload = {
        "candidate": _candidate_brief(resume_data),
        "job": {"title": job.get("title") or job.get("job_title"), "company": job.get("company")},
        "recruiter": recruiter or None,
        "original_message": original_message,
        "days_since_last_message": days_since,
        "follow_up_attempt": attempt_number,
    }
    user_message = f"Write the follow-up for:\n\n{json.dumps(payload, indent=2, ensure_ascii=False)}"

    async def call_groq() -> dict:
        client = get_client()
        resp = await client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": FOLLOW_SYSTEM},
                {"role": "user", "content": user_message},
            ],
        )
        return extract_json(resp.choices[0].message.content)

    async def call_gemini() -> dict:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction=FOLLOW_SYSTEM)
        resp = model.generate_content(user_message)
        return extract_json(resp.text)

    try:
        raw = await retry_async(call_groq, retries=3)
    except Exception as groq_error:
        logger.warning("[outreach] follow-up Groq failed: %s — trying Gemini", groq_error)
        try:
            raw = await retry_async(call_gemini, retries=2)
        except Exception as gemini_error:
            logger.error("[outreach] follow-up both providers failed: %s", gemini_error)
            return {"subject": "", "body": "", "new_angle": "", "should_send": True,
                    "confidence": "low", "warnings": ["Could not generate a follow-up. Try again."]}

    try:
        return FollowUpResponse(**raw).model_dump()
    except Exception as e:
        logger.warning("[outreach] follow-up schema validation failed: %s", e)
        return {"subject": raw.get("subject", ""), "body": raw.get("body", ""),
                "new_angle": raw.get("new_angle", ""), "should_send": True,
                "confidence": "low", "warnings": ["Response shape was unexpected; review before sending."]}


# ── Smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio

    resume = {
        "name": "Rahul Sharma",
        "summary": "Backend developer focused on Python APIs and data systems.",
        "skills": ["Python", "Django", "REST APIs", "PostgreSQL", "Docker", "AWS"],
        "experience_bullets": [
            "Built Django REST APIs serving 50k daily requests",
            "Cut PostgreSQL query latency 30% by adding composite indexes",
            "Containerised the deploy pipeline with Docker, halving release time",
        ],
    }
    job = {"title": "Backend Engineer", "company": "Stripe", "department": "Payments"}
    recruiter = {"name": "Priya", "role": "Technical Recruiter"}
    ctx = "Stripe recently expanded its India engineering team."

    out = asyncio.run(draft_outreach(resume, job, recruiter, ctx))
    print(json.dumps(out, indent=2))
