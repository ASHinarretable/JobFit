"""
scraper/recruiter_search.py
Free, best-effort discovery of the recruiter / hiring manager to contact for a
role — the "WHO do I email" half of outreach (contacts.py is the "what's their
address" half).

Two backends, chosen automatically:
  1. Google Custom Search JSON API — RELIABLE and production-grade. 100 free
     queries/day, then ~$5/1000. Used when GOOGLE_CSE_KEY and GOOGLE_CSE_ID are
     set. This is the path for the deployed backend.
  2. DuckDuckGo HTML — no key, but DDG 403s/challenges datacenter IPs, so it
     only really works from a residential IP (i.e. local dev). Best-effort
     fallback only.

Important architectural note: search engines block server/datacenter IPs by
design. The most robust place to discover a recruiter is the BROWSER EXTENSION,
which runs on the user's own IP and logged-in session — the job page they're
viewing often already names the hiring manager. Treat this server-side module
as the convenience path; the extension is the durable one.

Either backend runs the same "dork" query scoped to LinkedIn profiles, e.g.
    site:linkedin.com/in ("technical recruiter" OR "talent") "Stripe"
and parses result titles like
    "Priya Nair - Technical Recruiter at Stripe | LinkedIn"
into a name + headline + profile URL.

Never raises — returns whatever it found plus an honest note; empty is valid.
Chains naturally into contacts.guess_emails(name, domain).
"""
import asyncio
import html
import logging
import os
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import unquote, parse_qs, urlparse

import httpx

logger = logging.getLogger(__name__)

# Google Custom Search — set both env vars to enable the reliable backend.
_GOOGLE_CSE_KEY = os.getenv("GOOGLE_CSE_KEY", "")
_GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
_GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"

# Two free DDG HTML surfaces. 'lite' is the plainer, more automation-tolerant
# one and returns the real URL directly; 'html' is richer but stricter (and
# wraps links in a redirect). We try lite first, fall back to html.
_DDG_LITE = "https://lite.duckduckgo.com/lite/"
_DDG_HTML = "https://html.duckduckgo.com/html/"

# Browser-like headers. DDG 403s thin requests; a full header set with a
# Referer and Accept-Language is what makes it serve results to a script.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://duckduckgo.com/",
    "Origin": "https://duckduckgo.com",
    "Content-Type": "application/x-www-form-urlencoded",
}
_TIMEOUT = 15

# 'html' endpoint anchor: class="result__a" href="//duckduckgo.com/l/?uddg=<url>"
_RESULT_RE = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
# 'lite' endpoint anchor: <a ... class="result-link" href="<real url>">title</a>
_LITE_RE = re.compile(
    r'class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Role phrases that signal a person worth contacting, grouped by intent.
_RECRUITER_TERMS = [
    "technical recruiter", "talent acquisition", "recruiter",
    "talent partner", "sourcer", "recruiting",
]
_HIRING_MANAGER_TERMS = [
    "engineering manager", "hiring manager", "head of engineering",
    "engineering lead", "director of engineering",
]

# A LinkedIn title's name segment: 1-3 capitalised words, allowing ' - . accents.
_NAME_RE = re.compile(r"^([A-Z][A-Za-z.'À-ſ-]+(?:\s+[A-Z][A-Za-z.'À-ſ-]+){0,2})\b")


@dataclass
class RecruiterHit:
    name: str
    headline: str
    linkedin_url: str

    def to_dict(self) -> dict:
        return {"name": self.name, "headline": self.headline, "linkedin_url": self.linkedin_url}


def _decode_ddg_href(href: str) -> str:
    """DDG wraps result links in a /l/?uddg=<encoded-real-url> redirect."""
    if href.startswith("//"):
        href = "https:" + href
    try:
        q = parse_qs(urlparse(href).query)
        if "uddg" in q:
            return unquote(q["uddg"][0])
    except Exception:
        pass
    return href


def _clean_title(raw: str) -> str:
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub("", raw))).strip()


def _extract_name(title: str) -> Optional[str]:
    """
    Pull a plausible person-name from a LinkedIn result title. Titles look like
    'Priya Nair - Technical Recruiter at Stripe | LinkedIn'. We take the segment
    before the first ' - ' or ' | ' and sanity-check it looks like a name.
    """
    head = re.split(r"\s[-|–]\s", title, maxsplit=1)[0].strip()
    m = _NAME_RE.match(head)
    if not m:
        return None
    name = m.group(1).strip()
    # Reject obvious non-names (single lowercase word slipped through, company-ish).
    if len(name.split()) < 2 and "." not in name:
        return None
    return name


async def _fetch(url: str, query: str, client: httpx.AsyncClient) -> Optional[str]:
    """POST a DDG query to one endpoint; return HTML text or None. Never raises."""
    try:
        r = await client.post(url, data={"q": query, "kl": "us-en"},
                              headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning("[recruiter_search] %s failed: %s", url, e)
        return None


def _parse_lite(text: str) -> List[tuple[str, str]]:
    out: List[tuple[str, str]] = []
    for href, raw_title in _LITE_RE.findall(text):
        url = _decode_ddg_href(href)   # lite usually gives the real URL already
        if "linkedin.com/in" not in url:
            continue
        out.append((_clean_title(raw_title), url))
    return out


def _parse_html(text: str) -> List[tuple[str, str]]:
    out: List[tuple[str, str]] = []
    for href, raw_title in _RESULT_RE.findall(text):
        url = _decode_ddg_href(href)
        if "linkedin.com/in" not in url:
            continue
        out.append((_clean_title(raw_title), url))
    return out


async def _ddg_search(query: str, client: httpx.AsyncClient) -> List[tuple[str, str]]:
    """
    Run one query against DDG, trying the tolerant 'lite' endpoint first and the
    'html' endpoint as a fallback. Returns [(title, real_url), ...]. Never raises.
    """
    lite = await _fetch(_DDG_LITE, query, client)
    if lite:
        hits = _parse_lite(lite)
        if hits:
            return hits
    html_text = await _fetch(_DDG_HTML, query, client)
    if html_text:
        return _parse_html(html_text)
    return []


def _cse_enabled() -> bool:
    return bool(_GOOGLE_CSE_KEY and _GOOGLE_CSE_ID)


async def _google_search(query: str, client: httpx.AsyncClient, num: int = 8) -> List[tuple[str, str]]:
    """
    Run one query via Google Custom Search JSON API. Reliable from any IP.
    Returns [(title, link), ...]. Never raises.
    """
    try:
        r = await client.get(
            _GOOGLE_CSE_URL,
            params={"key": _GOOGLE_CSE_KEY, "cx": _GOOGLE_CSE_ID, "q": query, "num": num},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        logger.warning("[recruiter_search] Google CSE failed: %s", e)
        return []

    out: List[tuple[str, str]] = []
    for it in items:
        link = it.get("link", "")
        if "linkedin.com/in" not in link:
            continue
        out.append((_clean_title(it.get("title", "")), link))
    return out


async def _search(query: str, client: httpx.AsyncClient) -> List[tuple[str, str]]:
    """Pick the best available backend: Google CSE if configured, else DDG."""
    if _cse_enabled():
        return await _google_search(query, client)
    return await _ddg_search(query, client)


def _build_query(company: str, terms: List[str], extra: str = "") -> str:
    term_clause = " OR ".join(f'"{t}"' for t in terms)
    extra_clause = f' "{extra}"' if extra.strip() else ""
    return f'site:linkedin.com/in ({term_clause}) "{company}"{extra_clause}'


async def find_recruiters(
    company: str,
    role_hint: str = "",
    limit: int = 5,
) -> dict:
    """
    Find likely recruiters AND hiring managers at a company.

    Args:
        company:   company name as it appears on LinkedIn (e.g. "Stripe")
        role_hint: optional extra term to narrow, e.g. "engineering" or the
                   department, so we surface the right recruiter at a big company
        limit:     max people to return per category

    Returns a dict with 'recruiters', 'hiring_managers', and an honest 'note'.
    Never raises; empty lists are a valid (and common) result.
    """
    company = (company or "").strip()
    if not company:
        return {"company": company, "recruiters": [], "hiring_managers": [],
                "note": "No company supplied."}

    q_recruiter = _build_query(company, _RECRUITER_TERMS, role_hint)
    q_manager = _build_query(company, _HIRING_MANAGER_TERMS, role_hint)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        recruiter_raw, manager_raw = await asyncio.gather(
            _search(q_recruiter, client),
            _search(q_manager, client),
        )

    def _dedupe(rows: List[tuple[str, str]]) -> List[RecruiterHit]:
        seen: set[str] = set()
        hits: List[RecruiterHit] = []
        for title, url in rows:
            name = _extract_name(title)
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            hits.append(RecruiterHit(name=name, headline=title, linkedin_url=url))
            if len(hits) >= limit:
                break
        return hits

    recruiters = _dedupe(recruiter_raw)
    managers = _dedupe(manager_raw)

    backend = "google_cse" if _cse_enabled() else "duckduckgo"
    note = (
        "Best-effort results parsed from public search — verify each person "
        "actually works at the company before reaching out. "
    )
    if not recruiters and not managers:
        if backend == "duckduckgo":
            note += (
                "Search returned nothing. DuckDuckGo blocks automated queries from "
                "datacenter IPs, so this rarely works on a deployed server — set "
                "GOOGLE_CSE_KEY and GOOGLE_CSE_ID for reliable results, or run "
                "discovery from the browser extension."
            )
        else:
            note += "Search returned nothing — try a different company spelling or role hint."

    return {
        "company": company,
        "backend": backend,
        "recruiters": [h.to_dict() for h in recruiters],
        "hiring_managers": [h.to_dict() for h in managers],
        "note": note,
    }


# ── Smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    out = asyncio.run(find_recruiters("Stripe", role_hint="engineering"))
    print(json.dumps(out, indent=2))
