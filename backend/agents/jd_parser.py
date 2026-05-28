"""
agents/jd_parser.py  —  AGENT 2
Reads raw job description → extracts what the employer actually wants.
Model: Groq Llama-3.3-70b (free)
"""
import json, os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ════════════════════════════════════════════════════════════
#  PROMPT
# ════════════════════════════════════════════════════════════
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
  "soft_skills": ["communication", "teamwork", etc],

  "experience_required": "e.g. 0-1 years / 2+ years / fresher / not specified",
  "education_required": "e.g. B.Tech CS / Any degree / not specified",

  "keywords": [
    "COMPREHENSIVE list — every technical term an ATS would scan for.
     Include synonyms: e.g. both 'REST' and 'REST API' and 'RESTful'"
  ],

  "keyword_frequency": {
    "Python": 4,
    "Docker": 2
  },

  "must_have_phrases": [
    "exact multi-word phrases from the JD that should appear on the resume"
  ],

  "red_flags_if_missing": [
    "the 3-5 skills so critical that missing them likely means instant rejection"
  ],

  "responsibilities": ["key responsibilities listed in the JD"],

  "industry_context": "one sentence about what this role/company does"
}

Rules:
- Return ONLY the JSON object.
- keywords must be exhaustive — this is what we compare against the resume.
- keyword_frequency: count how many times each important keyword appears (higher = more critical).
- red_flags_if_missing: only the truly non-negotiable ones.
"""

async def parse_jd(text: str) -> dict:
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.05,
            max_tokens=2000,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": f"Parse this job description:\n\n{text[:5000]}"}
            ]
        )
        raw = resp.choices[0].message.content.strip()
        raw = _clean(raw)
        return json.loads(raw)
    except Exception as e:
        print(f"[jd_parser] {e}")
        return {"required_skills": [], "keywords": [], "red_flags_if_missing": []}

def _clean(s: str) -> str:
    if "```" in s:
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    return s.strip()
