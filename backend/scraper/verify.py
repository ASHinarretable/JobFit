"""
scraper/verify.py
Check whether a company slug returns live jobs before adding it to the registry.

    python -m scraper.verify stripe                 # try both providers
    python -m scraper.verify acme --ats greenhouse  # try one provider
"""
import argparse
import httpx

_H = {"User-Agent": "Mozilla/5.0 (compatible; JobFit/1.0)"}


def _check_greenhouse(slug: str) -> int:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    r = httpx.get(url, headers=_H, timeout=15)
    return len(r.json().get("jobs", [])) if r.status_code == 200 else 0


def _check_lever(slug: str) -> int:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = httpx.get(url, headers=_H, timeout=15)
    data = r.json()
    return len(data) if r.status_code == 200 and isinstance(data, list) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--ats", choices=["greenhouse", "lever"], default=None)
    args = ap.parse_args()

    providers = [args.ats] if args.ats else ["greenhouse", "lever"]
    found = False
    for ats in providers:
        try:
            n = _check_greenhouse(args.slug) if ats == "greenhouse" else _check_lever(args.slug)
        except Exception as e:
            print(f"  {ats:11} error: {e}")
            continue
        mark = "OK " if n > 0 else "—  "
        print(f"  {mark}{ats:11} {n} jobs")
        if n > 0:
            found = True
            print(f"\n  Add to registry.py:\n"
                  f'    Company("{args.slug.title()}", "{ats}", "{args.slug}"),')
    if not found:
        print("\n  No jobs found — not a public Greenhouse/Lever board, or wrong slug.")


if __name__ == "__main__":
    main()
