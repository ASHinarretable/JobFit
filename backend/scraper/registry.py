"""
scraper/registry.py
Maps companies → their ATS provider + board slug.

Every slug here was verified live against the provider's public API. Adding a
company is a one-line edit; to confirm a new slug works before adding it, run:
    python -m scraper.verify <slug>

This is the only piece that needs manual curation. Once a company is in the
registry, its jobs flow in for free, forever, with zero scraping risk.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    name: str          # display name
    ats: str           # "greenhouse" | "lever"
    slug: str          # board token used in the API URL


# Verified 2026 — each returns live jobs from its provider's public API.
REGISTRY: list[Company] = [
    # ── Greenhouse ──────────────────────────────────────────
    Company("Stripe",      "greenhouse", "stripe"),
    Company("Airbnb",      "greenhouse", "airbnb"),
    Company("Coinbase",    "greenhouse", "coinbase"),
    Company("Databricks",  "greenhouse", "databricks"),
    Company("Dropbox",     "greenhouse", "dropbox"),
    Company("Robinhood",   "greenhouse", "robinhood"),
    Company("GitLab",      "greenhouse", "gitlab"),
    Company("Instacart",   "greenhouse", "instacart"),
    Company("Brex",        "greenhouse", "brex"),
    Company("Discord",     "greenhouse", "discord"),
    Company("Reddit",      "greenhouse", "reddit"),
    Company("Figma",       "greenhouse", "figma"),
    Company("Asana",       "greenhouse", "asana"),
    Company("Flexport",    "greenhouse", "flexport"),
    Company("Samsara",     "greenhouse", "samsara"),
    Company("Airtable",    "greenhouse", "airtable"),
    Company("Anthropic",   "greenhouse", "anthropic"),
    Company("SoFi",        "greenhouse", "sofi"),
    Company("Affirm",      "greenhouse", "affirm"),
    # ── Lever ───────────────────────────────────────────────
    Company("Spotify",     "lever", "spotify"),
    Company("Mistral AI",  "lever", "mistral"),
]


def all_companies() -> list[Company]:
    return list(REGISTRY)


def find(slug: str) -> Company | None:
    return next((c for c in REGISTRY if c.slug == slug), None)
