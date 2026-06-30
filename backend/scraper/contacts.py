"""
scraper/contacts.py
Free, zero-dependency email-pattern discovery for recruiter outreach.

The paid tools (Hunter.io, Apollo, Proxycurl) charge per lookup to do exactly
this. We don't pay. Given a person's name and a company email domain, we
generate the candidate addresses in the order companies most commonly use
them, so the user can try the top guess first.

What this module does NOT do (deliberately, for now):
  - SMTP RCPT-TO verification — checking whether an address actually exists by
    opening an SMTP conversation. It's doable and free, but many hosts (Google
    Workspace especially) return ambiguous results, greylist, or block the
    probing IP, and doing it from a server can hurt that IP's reputation. It's
    a follow-up to design carefully, not something to bolt on naively.
  - Domain discovery from a company name. We ask the caller to supply the
    domain (it's usually obvious from the careers page / job URL), rather than
    guess "stripe" -> "stripe.com" unreliably.

So this is honest about what it is: a ranked list of *likely* addresses, not
verified ones. The UI should present them as "most likely" and let the user
pick.
"""
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse

# Ordered by real-world prevalence across companies (most common first).
# {first}/{last}/{f}/{l} are filled per-person; {domain} is the company domain.
_PATTERNS = [
    "{first}.{last}@{domain}",   # jane.doe@   — by far the most common
    "{first}@{domain}",          # jane@       — common at startups
    "{f}{last}@{domain}",        # jdoe@
    "{first}{last}@{domain}",    # janedoe@
    "{first}_{last}@{domain}",   # jane_doe@
    "{last}.{first}@{domain}",   # doe.jane@
    "{f}.{last}@{domain}",       # j.doe@
    "{first}.{l}@{domain}",      # jane.d@
    "{last}@{domain}",           # doe@
]

# Common recruiting inbox aliases — useful when no individual is known.
_ROLE_ALIASES = ["careers", "jobs", "recruiting", "talent", "hr", "hiring"]

_CLEAN_RE = re.compile(r"[^a-z]")


@dataclass
class EmailGuess:
    email: str
    pattern: str
    rank: int          # 1 = most likely

    def to_dict(self) -> dict:
        return {"email": self.email, "pattern": self.pattern, "rank": self.rank}


def _normalize_name_part(part: str) -> str:
    """Lowercase, strip accents-as-best-we-can, drop non-letters."""
    return _CLEAN_RE.sub("", part.strip().lower())


def split_name(full_name: str) -> tuple[str, str]:
    """
    Split a display name into (first, last). Handles single names and
    middle names (middle is ignored). Returns ('', '') if unusable.
    """
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if not parts:
        return "", ""
    first = _normalize_name_part(parts[0])
    last = _normalize_name_part(parts[-1]) if len(parts) > 1 else ""
    return first, last


def normalize_domain(domain_or_url: str) -> str:
    """
    Accept a bare domain ('stripe.com'), a full URL, or an email, and return
    just the registrable domain ('stripe.com'). Strips a leading 'www.'.
    """
    s = (domain_or_url or "").strip().lower()
    if not s:
        return ""
    if "@" in s:                       # an email was passed
        return s.split("@", 1)[1]
    if "://" in s:                     # a URL was passed
        s = urlparse(s).netloc or s
    s = s.split("/", 1)[0]             # drop any path
    if s.startswith("www."):
        s = s[4:]
    return s


def guess_emails(full_name: str, domain_or_url: str, limit: int = 6) -> List[EmailGuess]:
    """
    Generate ranked candidate email addresses for a named person at a domain.

    Returns an empty list if the name or domain can't be parsed.
    """
    domain = normalize_domain(domain_or_url)
    first, last = split_name(full_name)
    if not domain or not first:
        return []

    f = first[0] if first else ""
    l = last[0] if last else ""
    fields = {"first": first, "last": last, "f": f, "l": l, "domain": domain}

    guesses: List[EmailGuess] = []
    seen: set[str] = set()
    for pattern in _PATTERNS:
        # Patterns needing a last name are useless when we only have one name.
        if not last and ("{last}" in pattern or "{l}" in pattern):
            continue
        email = pattern.format(**fields)
        if email in seen:
            continue
        seen.add(email)
        guesses.append(EmailGuess(email=email, pattern=pattern, rank=len(guesses) + 1))
        if len(guesses) >= limit:
            break
    return guesses


def role_inbox_guesses(domain_or_url: str) -> List[str]:
    """Generic recruiting inboxes to fall back on when no person is known."""
    domain = normalize_domain(domain_or_url)
    if not domain:
        return []
    return [f"{alias}@{domain}" for alias in _ROLE_ALIASES]


def discover_contacts(
    full_name: Optional[str],
    domain_or_url: str,
    limit: int = 6,
) -> dict:
    """
    One call for the outreach flow: returns ranked personal guesses (if a name
    is known) plus role-inbox fallbacks. Caller decides what to surface.
    """
    domain = normalize_domain(domain_or_url)
    personal = guess_emails(full_name, domain_or_url, limit) if full_name else []
    return {
        "domain": domain,
        "named_guesses": [g.to_dict() for g in personal],
        "role_inboxes": role_inbox_guesses(domain_or_url),
        "verified": False,   # honest: these are guesses, not SMTP-verified
        "note": (
            "These are the most statistically likely addresses, not verified "
            "ones. Try the top-ranked guess first."
        ),
    }


# ── Smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    print(json.dumps(discover_contacts("Priya Nair", "https://stripe.com/careers"), indent=2))
    print(json.dumps(discover_contacts("Madonna", "lever.co"), indent=2))
    print(json.dumps(discover_contacts(None, "airbnb.com"), indent=2))
