"""
scraper/ranker.py
Fast, free, LLM-free ranking of scraped jobs against a candidate's resume.

Design choice: the LIST view must be instant and cost nothing. Running the
LLM gap-analyzer on 800 jobs would be slow and expensive. So we rank with a
cheap lexical overlap score here, and only spend an LLM call (the full
analyze_gaps pipeline) once the user opens a specific job.

The score is a 0–100 keyword-overlap percentage between the resume's keywords
and the job's text, lightly boosted when keywords hit the job *title* (a title
match is a far stronger signal than a body mention).
"""
import re
from dataclasses import dataclass

from scraper.sources import Job

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")

# Common words that pollute overlap scoring without signaling skill fit.
_STOP = {
    "the", "and", "for", "with", "you", "your", "our", "are", "will", "this",
    "that", "have", "from", "their", "they", "all", "can", "who", "what",
    "job", "role", "work", "team", "experience", "years", "year", "skills",
    "ability", "strong", "good", "new", "etc", "including", "across",
}


@dataclass
class RankedJob:
    job: Job
    match_score: int
    matched_keywords: list[str]

    def to_dict(self) -> dict:
        d = self.job.to_dict()
        d["match_score"] = self.match_score
        d["matched_keywords"] = self.matched_keywords
        # Short preview for the card; full text kept so "Tailor my resume"
        # needs no second round-trip to the company's board.
        d["description_preview"] = self.job.description[:280]
        d["description"] = self.job.description
        return d


def _tokenize(text: str) -> set[str]:
    return {
        t for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 2 and t not in _STOP
    }


def _resume_keywords(resume_data: dict) -> set[str]:
    """
    Prefer the structured keywords the resume parser already extracted; fall
    back to tokenizing skills + the raw text if needed.
    """
    kws: set[str] = set()
    for k in resume_data.get("all_keywords", []):
        kws |= _tokenize(str(k))
    for s in resume_data.get("skills", []):
        kws |= _tokenize(str(s))
    if not kws:
        kws = _tokenize(resume_data.get("_raw", ""))
    return kws


def score_job(resume_kws: set[str], job: Job) -> RankedJob:
    title_tokens = _tokenize(job.title)
    body_tokens = _tokenize(job.description)
    job_tokens = title_tokens | body_tokens
    if not job_tokens or not resume_kws:
        return RankedJob(job=job, match_score=0, matched_keywords=[])

    matched = resume_kws & job_tokens
    # Base: what fraction of the CANDIDATE'S skills this job actually asks for.
    # (Recall from the resume's perspective — intuitive and well-scaled, since
    # a resume has ~15-40 keywords, not the hundreds a JD body contains.)
    coverage = len(matched) / max(len(resume_kws), 1)
    # Title boost: a keyword in the title is a far stronger signal than one
    # buried in the body ("Backend Engineer" vs. a passing mention of Python).
    title_hits = resume_kws & title_tokens
    boost = min(len(title_hits) * 0.05, 0.25)

    score = int(min((coverage + boost) * 100, 100))
    return RankedJob(
        job=job,
        match_score=score,
        matched_keywords=sorted(matched, key=len, reverse=True)[:12],
    )


def rank_jobs(resume_data: dict, jobs: list[Job]) -> list[RankedJob]:
    resume_kws = _resume_keywords(resume_data)
    ranked = [score_job(resume_kws, j) for j in jobs]
    ranked.sort(key=lambda r: r.match_score, reverse=True)
    return ranked
