"""
scraper/search.py
The public entry point for job search: fetch → filter → rank.

Filters mirror the UI navbar spec:
  - query           free text matched against the title (e.g. "backend")
  - location        substring match on the job's location
  - remote_only     only remote/anywhere roles
  - domain          software | data | finance | marketing | sales | design | product
  - experience      intern | junior | mid | senior  (best-effort from the title)
  - posted_within_hours   recency cutoff (e.g. 24)
  - companies       restrict to specific registry slugs
  - limit           max results returned
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from scraper.registry import all_companies, find
from scraper.sources import Job, fetch_all_jobs
from scraper.ranker import rank_jobs, RankedJob

logger = logging.getLogger(__name__)

# Domain → keywords we expect in the title or department.
_DOMAIN_HINTS = {
    "software":  ["engineer", "developer", "software", "backend", "frontend",
                  "full stack", "fullstack", "sre", "devops", "platform", "mobile"],
    "data":      ["data", "machine learning", "ml", "ai ", "analytics",
                  "scientist", "analyst", "research"],
    "finance":   ["finance", "financial", "accounting", "fp&a", "treasury",
                  "controller", "audit"],
    "marketing": ["marketing", "growth", "brand", "content", "seo", "demand gen"],
    "sales":     ["sales", "account executive", "account manager", "business development",
                  "revenue", "partnerships"],
    "design":    ["design", "designer", "ux", "ui", "product design", "research"],
    "product":   ["product manager", "product management", "program manager", "product owner"],
}

# Experience level → tokens that appear in titles.
_EXPERIENCE_HINTS = {
    "intern":  ["intern", "internship", "co-op", "coop", "trainee"],
    "junior":  ["junior", "jr ", "associate", "entry", "i ", "graduate", "new grad"],
    "mid":     ["mid", "ii ", "iii "],
    "senior":  ["senior", "sr ", "staff", "principal", "lead", "manager", "director", "head of"],
}


@dataclass
class JobFilters:
    query: str = ""
    location: str = ""
    remote_only: bool = False
    domain: str = ""
    experience: str = ""
    posted_within_hours: int = 0
    companies: list[str] = field(default_factory=list)
    limit: int = 50


def _match_domain(job: Job, domain: str) -> bool:
    hints = _DOMAIN_HINTS.get(domain.lower())
    if not hints:
        return True
    blob = f"{job.title} {job.department}".lower()
    return any(h in blob for h in hints)


def _match_experience(job: Job, experience: str) -> bool:
    hints = _EXPERIENCE_HINTS.get(experience.lower())
    if not hints:
        return True
    title = f" {job.title.lower()} "
    return any(h in title for h in hints)


def _match_recency(job: Job, hours: int) -> bool:
    if not hours or not job.posted_at:
        return True
    try:
        posted = datetime.fromisoformat(job.posted_at.replace("Z", "+00:00"))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return posted >= datetime.now(timezone.utc) - timedelta(hours=hours)
    except Exception:
        return True  # don't drop a job just because its date didn't parse


def _passes(job: Job, f: JobFilters) -> bool:
    if f.query and f.query.lower() not in job.title.lower():
        return False
    if f.remote_only and not job.remote:
        return False
    if f.location and f.location.lower() not in job.location.lower():
        return False
    if not _match_domain(job, f.domain):
        return False
    if not _match_experience(job, f.experience):
        return False
    if not _match_recency(job, f.posted_within_hours):
        return False
    return True


async def search_jobs(resume_data: dict, filters: JobFilters) -> dict:
    """
    Fetch jobs from the registry, apply filters, rank against the resume.
    Returns a JSON-serializable dict for the API.
    """
    if filters.companies:
        companies = [c for c in (find(s) for s in filters.companies) if c]
    else:
        companies = all_companies()

    jobs = await fetch_all_jobs(companies)
    filtered = [j for j in jobs if _passes(j, filters)]
    ranked: list[RankedJob] = rank_jobs(resume_data, filtered)
    top = ranked[: filters.limit]

    return {
        "total_scanned": len(jobs),
        "total_matched": len(filtered),
        "returned": len(top),
        "jobs": [r.to_dict() for r in top],
    }
