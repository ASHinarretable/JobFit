"""
agents/graph.py  —  LangGraph orchestration

Replaces the old linear pipeline.py with a proper state machine:

        START
        ├──────────────┐         (parse_resume and parse_jd run in parallel —
   parse_resume    parse_jd       they're independent, so we fan out)
        └──────┬───────┘
          analyze_gaps
               │
        ┌──────┴───────┐          (conditional edge: don't waste an LLM call
     rewrite       skip_rewrite    rewriting a resume that barely matches)
        └──────┬───────┘
              END

Why LangGraph instead of `await a; await b; await c`:
- Conditional routing (skip the rewriter on a hopeless match)
- Parallel fan-out of the two independent parsers
- Per-node state is inspectable, which makes debugging the pipeline sane
- Drop-in place to add nodes later (interview-prep agent, outreach drafter)
"""
import asyncio
import logging
import os
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from agents.resume_parser import parse_resume
from agents.jd_parser import parse_jd
from agents.gap_analyzer import analyze_gaps
from agents.rewriter import rewrite_bullets

logger = logging.getLogger(__name__)

# Below this match score, tailoring the resume is a poor use of the user's
# time (and an LLM call) — we tell them to look elsewhere instead.
REWRITE_THRESHOLD = int(os.getenv("REWRITE_THRESHOLD", "40"))


class JobState(TypedDict, total=False):
    # Inputs
    resume_text: str
    jd_text: str
    # Populated by the parser nodes
    resume_data: dict
    jd_data: dict
    # Populated by the analysis / rewrite nodes
    gap_result: dict
    rewrite_result: dict
    # Routing breadcrumb so the API can tell the user why rewriting was skipped
    rewrite_skipped: bool


# ── Nodes ─────────────────────────────────────────────────────
# Each node takes the current state and returns ONLY the keys it writes.
# LangGraph merges the partial dict back into the shared state. Because the
# two parser nodes write disjoint keys, they can safely run in parallel.

async def parse_resume_node(state: JobState) -> dict:
    logger.info("[graph] node=parse_resume")
    return {"resume_data": await parse_resume(state["resume_text"])}


async def parse_jd_node(state: JobState) -> dict:
    logger.info("[graph] node=parse_jd")
    return {"jd_data": await parse_jd(state["jd_text"])}


async def analyze_gaps_node(state: JobState) -> dict:
    logger.info("[graph] node=analyze_gaps")
    return {"gap_result": await analyze_gaps(state["resume_data"], state["jd_data"])}


async def rewrite_node(state: JobState) -> dict:
    logger.info("[graph] node=rewrite")
    result = await rewrite_bullets(
        state["resume_data"].get("experience_bullets", []),
        state["jd_data"].get("keywords", []),
    )
    return {"rewrite_result": result, "rewrite_skipped": False}


async def skip_rewrite_node(state: JobState) -> dict:
    score = state["gap_result"].get("overall_score", 0)
    logger.info("[graph] node=skip_rewrite score=%s", score)
    return {
        "rewrite_result": {
            "suggestions": [],
            "summary": "",
            "extra_bullets": [],
            "skipped_reason": (
                f"Match score is {score}% — below the {REWRITE_THRESHOLD}% "
                "threshold. Tailoring won't meaningfully help here; this role "
                "likely isn't a fit. Focus your energy on closer matches."
            ),
        },
        "rewrite_skipped": True,
    }


def _route_after_gaps(state: JobState) -> str:
    score = state["gap_result"].get("overall_score", 0)
    return "rewrite" if score >= REWRITE_THRESHOLD else "skip_rewrite"


# ── Graph assembly ────────────────────────────────────────────
def _build_graph():
    g = StateGraph(JobState)

    g.add_node("parse_resume", parse_resume_node)
    g.add_node("parse_jd", parse_jd_node)
    g.add_node("analyze_gaps", analyze_gaps_node)
    g.add_node("rewrite", rewrite_node)
    g.add_node("skip_rewrite", skip_rewrite_node)

    # Fan out: both parsers start from START and run concurrently
    g.add_edge(START, "parse_resume")
    g.add_edge(START, "parse_jd")

    # Fan in: analyze_gaps waits for BOTH parsers to finish
    g.add_edge("parse_resume", "analyze_gaps")
    g.add_edge("parse_jd", "analyze_gaps")

    # Conditional branch on the match score
    g.add_conditional_edges(
        "analyze_gaps",
        _route_after_gaps,
        {"rewrite": "rewrite", "skip_rewrite": "skip_rewrite"},
    )

    g.add_edge("rewrite", END)
    g.add_edge("skip_rewrite", END)

    return g.compile()


# Compile once at import time — the graph is stateless and reusable.
_GRAPH = _build_graph()


async def run_analysis(resume_text: str, job_description: str) -> dict:
    """
    Run the full 4-agent analysis through the LangGraph state machine.
    Returns the same flat shape the API/frontend already expect.
    """
    final: JobState = await _GRAPH.ainvoke(
        {"resume_text": resume_text, "jd_text": job_description}
    )

    gap = final.get("gap_result", {})
    rewrite = final.get("rewrite_result", {})

    return {
        "match_score":        gap.get("overall_score", 0),
        "section_scores":     gap.get("section_scores", {}),
        "missing_keywords":   gap.get("missing_keywords", []),
        "present_keywords":   gap.get("present_keywords", []),
        "format_issues":      gap.get("format_issues", []),
        "quick_wins":         gap.get("quick_wins", []),
        "honest_assessment":  gap.get("honest_assessment", ""),
        "strengths":          gap.get("strengths", []),
        "score_to_75":        gap.get("score_to_reach_75_percent", []),
        "rewritten_bullets":  rewrite.get("suggestions", []),
        "summary_suggestion": rewrite.get("summary", ""),
        "rewrite_skipped":    final.get("rewrite_skipped", False),
        "skipped_reason":     rewrite.get("skipped_reason", ""),
    }


# ── Smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    import json

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
    out = asyncio.run(run_analysis(resume, jd))
    print(json.dumps(out, indent=2))
