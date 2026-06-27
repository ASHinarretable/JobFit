# pipeline.py
# Runs all 4 agents in sequence.
# Input:  resume text + job description text
# Output: complete analysis as a Python dict
# No server, no frontend — pure Python. 

import json
from agents.resume_parser import parse_resume
from agents.jd_parser import parse_jd
from agents.gap_analyzer import analyze_gaps
from agents.rewriter import rewrite_bullets
import asyncio


async def run_pipeline(resume_text: str, job_description: str) -> dict:

    print("Running Agent 1 — parsing resume...")
    resume_data = await parse_resume(resume_text)

    print("Running Agent 2 — parsing job description...")
    jd_data = await parse_jd(job_description)

    print("Running Agent 3 — analyzing gaps...")
    gap_result = await analyze_gaps(resume_data, jd_data)

    print("Running Agent 4 — rewriting bullets...")
    rewrite_result = await rewrite_bullets(
        resume_data.get("experience_bullets", []),
        jd_data.get("keywords", [])
    )

    return {
        "match_score":        gap_result.get("overall_score", 0),
        "section_scores":     gap_result.get("section_scores", {}),
        "missing_keywords":   gap_result.get("missing_keywords", []),
        "present_keywords":   gap_result.get("present_keywords", []),
        "quick_wins":         gap_result.get("quick_wins", []),
        "honest_assessment":  gap_result.get("honest_assessment", ""),
        "rewritten_bullets":  rewrite_result.get("suggestions", []),
        "summary_suggestion": rewrite_result.get("summary", ""),
    }


# ── Test it ───────────────────────────────────────────────────
if __name__ == "__main__":

    resume = """
    Rahul Sharma — rahul@email.com
    Skills: Python, Django, REST APIs, PostgreSQL, Git
    Experience:
    Backend Intern — Webify Solutions (2023)
    - Built API endpoints using Django REST Framework
    - Optimised slow SQL queries, reducing load time by 30%
    Projects:
    StudySync — Flask, SQLite, deployed on Heroku
    Education: B.Tech CS — Mumbai University 2024
    """

    jd = """
    Backend Developer — FinTech startup
    We are looking for a Python developer with experience in Django,
    REST APIs, Docker, PostgreSQL, and AWS. Agile team, fast-paced environment.
    Must have: Python, Django, REST API, SQL
    Nice to have: Docker, AWS, Redis, CI/CD
    """

    result = asyncio.run(run_pipeline(resume, jd))
    print(json.dumps(result, indent=2))