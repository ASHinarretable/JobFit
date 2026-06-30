"""
scraper/sources.py
Fetch jobs from Greenhouse / Lever public APIs and normalize them into one
common shape the rest of the app can rank, filter, and display.
"""
import asyncio
import html
import logging
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone

import httpx

from scraper.registry import Company, all_companies

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobFit/1.0)"}
_TIMEOUT = 15
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    department: str
    url: str
    description: str            # plain text
    posted_at: str             # ISO-8601, or "" if unknown
    remote: bool
    source: str                # "greenhouse" | "lever"

    def to_dict(self) -> dict:
        return asdict(self)


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    # Greenhouse double-escapes its content (e.g. "&lt;h2&gt;"), so unescape
    # entities into real tags FIRST, then strip the tags.
    text = html.unescape(raw)
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _looks_remote(*parts: str) -> bool:
    blob = " ".join(p.lower() for p in parts if p)
    return "remote" in blob or "anywhere" in blob


# ── Greenhouse ────────────────────────────────────────────────
def _parse_greenhouse(company: Company, payload: dict) -> list[Job]:
    jobs: list[Job] = []
    for j in payload.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "") or ""
        depts = j.get("departments") or []
        dept = depts[0].get("name", "") if depts else ""
        jobs.append(Job(
            id=f"gh-{company.slug}-{j.get('id')}",
            title=j.get("title", "").strip(),
            company=company.name,
            location=loc,
            department=dept,
            url=j.get("absolute_url", ""),
            description=_strip_html(j.get("content", "")),
            posted_at=j.get("updated_at") or j.get("first_published") or "",
            remote=_looks_remote(loc, j.get("title", "")),
            source="greenhouse",
        ))
    return jobs


async def _fetch_greenhouse(client: httpx.AsyncClient, company: Company) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company.slug}/jobs?content=true"
    r = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    return _parse_greenhouse(company, r.json())


# ── Lever ─────────────────────────────────────────────────────
def _lever_iso(created_ms) -> str:
    if not created_ms:
        return ""
    try:
        return datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return ""


def _parse_lever(company: Company, payload: list) -> list[Job]:
    jobs: list[Job] = []
    for j in payload:
        cats = j.get("categories") or {}
        loc = cats.get("location", "") or ""
        workplace = j.get("workplaceType", "") or ""
        jobs.append(Job(
            id=f"lv-{company.slug}-{j.get('id')}",
            title=j.get("text", "").strip(),
            company=company.name,
            location=loc,
            department=cats.get("department", "") or cats.get("team", "") or "",
            url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
            description=j.get("descriptionPlain", "") or _strip_html(j.get("description", "")),
            posted_at=_lever_iso(j.get("createdAt")),
            remote=_looks_remote(loc, workplace, j.get("text", "")),
            source="lever",
        ))
    return jobs


async def _fetch_lever(client: httpx.AsyncClient, company: Company) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{company.slug}?mode=json"
    r = await client.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    return _parse_lever(company, r.json())


# ── Orchestration ─────────────────────────────────────────────
async def _fetch_one(client: httpx.AsyncClient, company: Company) -> list[Job]:
    try:
        if company.ats == "greenhouse":
            return await _fetch_greenhouse(client, company)
        if company.ats == "lever":
            return await _fetch_lever(client, company)
        logger.warning("[scraper] unknown ats=%s for %s", company.ats, company.slug)
        return []
    except Exception as e:
        # One dead board must never sink the whole search.
        logger.warning("[scraper] %s (%s) failed: %s", company.slug, company.ats, e)
        return []


async def fetch_all_jobs(companies: list[Company] | None = None) -> list[Job]:
    """
    Concurrently fetch jobs from every company in the registry (or a subset).
    Failures are isolated per-company.
    """
    companies = companies or all_companies()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_fetch_one(client, c) for c in companies)
        )
    jobs = [job for sub in results for job in sub]
    logger.info("[scraper] fetched %d jobs from %d companies", len(jobs), len(companies))
    return jobs


# ── Smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from scraper.registry import REGISTRY
    subset = REGISTRY[:3]  # keep the smoke test fast
    all_jobs = asyncio.run(fetch_all_jobs(subset))
    print(f"\nTotal: {len(all_jobs)} jobs")
    for jb in all_jobs[:3]:
        print(f"\n[{jb.company}] {jb.title}")
        print(f"  loc={jb.location!r} dept={jb.department!r} remote={jb.remote}")
        print(f"  desc={jb.description[:100]!r}")
