"""
agents/gap_analyzer.py  —  AGENT 3
Compares resume vs JD → match score, gaps, quick wins.
Model: Groq Llama-3.3-70b (free)
"""
import json, os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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

async def analyze_gaps(resume: dict, jd: dict) -> dict:
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

    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0.15,
            max_tokens=2800,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content":
                    f"RESUME DATA:\n{json.dumps(r, indent=2)}\n\n"
                    f"JD DATA:\n{json.dumps(j, indent=2)}\n\n"
                    "Produce the gap analysis JSON."}
            ]
        )
        raw = resp.choices[0].message.content.strip()
        raw = _clean(raw)
        data = json.loads(raw)
        data["overall_score"] = max(0, min(100, int(data.get("overall_score", 0))))
        return data
    except Exception as e:
        print(f"[gap_analyzer] {e}")
        return {"overall_score": 0, "section_scores": {}, "missing_keywords": [],
                "present_keywords": [], "format_issues": [], "quick_wins": [],
                "honest_assessment": "Analysis failed. Please try again.", "strengths": []}

def _clean(s: str) -> str:
    if "```" in s:
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    return s.strip()
