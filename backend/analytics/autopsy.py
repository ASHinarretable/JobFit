"""
analytics/autopsy.py
The "application autopsy" — analyse a user's application history and tell them,
in plain numbers, what's actually moving their reply rate.

Design choice: this is DETERMINISTIC, not an LLM. Every insight is a real
statistic the user can trust ("your reply rate triples above match score 70"),
computed from their own data. An LLM narrative can sit on top later, but the
core must be honest arithmetic — that's what builds trust and it costs nothing.

Input: a list of application records. The expected (loose) shape per record:
    {
        "company":        str,
        "title":          str,
        "match_score":    int,         # 0-100, from the gap analyzer
        "tailored":       bool,        # did they tailor the resume for this one?
        "outreach_sent":  bool,        # did they message a recruiter?
        "status":         str,         # see _STATUSES below
        "applied_at":     str,         # ISO date (optional)
    }
Missing fields are tolerated — we compute what we can.

This is the feature flywheel: it needs the interaction log to exist, which is
exactly the data we must capture anyway for personalisation/collaborative
filtering. Build the log once, feed both.
"""
from dataclasses import dataclass
from typing import List

# Funnel stages in order. A record's status implies it reached that stage and
# every stage before it (an "interview" record also counts as "replied").
_STATUSES = ["applied", "viewed", "replied", "interview", "offer", "rejected"]

# Which statuses count as "got a response" (recruiter engaged at all).
_RESPONDED = {"replied", "interview", "offer"}
# Which count as reaching an interview.
_INTERVIEWED = {"interview", "offer"}

# Match-score buckets for the correlation insight.
_BUCKETS = [(0, 50, "below 50"), (50, 70, "50–69"), (70, 101, "70+")]


@dataclass
class _Rate:
    label: str
    n: int
    responded: int

    @property
    def rate(self) -> float:
        return self.responded / self.n if self.n else 0.0


def _responded(rec: dict) -> bool:
    return str(rec.get("status", "")).lower() in _RESPONDED


def _interviewed(rec: dict) -> bool:
    return str(rec.get("status", "")).lower() in _INTERVIEWED


def _pct(x: float) -> int:
    return round(x * 100)


def _split_rate(records: List[dict], predicate, yes_label: str, no_label: str) -> dict:
    """Compare response rate between records matching a predicate and those not."""
    yes = [r for r in records if predicate(r)]
    no = [r for r in records if not predicate(r)]
    y = _Rate(yes_label, len(yes), sum(_responded(r) for r in yes))
    n = _Rate(no_label, len(no), sum(_responded(r) for r in no))
    return {
        "with": {"label": yes_label, "applications": y.n, "response_rate": _pct(y.rate)},
        "without": {"label": no_label, "applications": n.n, "response_rate": _pct(n.rate)},
        "lift_x": round(y.rate / n.rate, 1) if n.rate > 0 and y.n and n.n else None,
    }


def _funnel(records: List[dict]) -> dict:
    total = len(records)
    counts = {s: 0 for s in _STATUSES}
    for r in records:
        st = str(r.get("status", "applied")).lower()
        if st in _RESPONDED:
            counts["replied"] += 1
        if st in _INTERVIEWED:
            counts["interview"] += 1
        if st == "offer":
            counts["offer"] += 1
    return {
        "applied": total,
        "responded": counts["replied"],
        "interviews": counts["interview"],
        "offers": counts["offer"],
        "response_rate": _pct(counts["replied"] / total) if total else 0,
        "interview_rate": _pct(counts["interview"] / total) if total else 0,
    }


def _score_correlation(records: List[dict]) -> List[dict]:
    scored = [r for r in records if isinstance(r.get("match_score"), (int, float))]
    out = []
    for lo, hi, label in _BUCKETS:
        bucket = [r for r in scored if lo <= r["match_score"] < hi]
        if not bucket:
            continue
        resp = sum(_responded(r) for r in bucket)
        out.append({
            "bucket": label,
            "applications": len(bucket),
            "response_rate": _pct(resp / len(bucket)),
        })
    return out


def _effect_is_positive(effect: dict) -> bool:
    """
    True when the 'with' group genuinely outperforms 'without' and we have
    enough records in BOTH groups to mean anything. Handles the infinite-lift
    case (without == 0%) that a simple lift_x > 1 check would miss.
    """
    w, wo = effect.get("with", {}), effect.get("without", {})
    if not w.get("applications") or not wo.get("applications"):
        return False
    return w.get("response_rate", 0) > wo.get("response_rate", 0)


def _lift_phrase(effect: dict) -> str:
    """' (4.0× more)' when a finite multiplier exists, else ''."""
    return f" ({effect['lift_x']}× more)" if effect.get("lift_x") else ""


def _insights(funnel: dict, score_corr: List[dict], tailoring: dict, outreach: dict,
              n: int) -> List[str]:
    """Turn the stats into plain-language, honest, actionable lines."""
    insights: List[str] = []

    if n < 5:
        insights.append(
            f"Only {n} applications logged so far — these numbers will get sharper "
            "after ~10. Keep going."
        )

    # The headline correlation: does a higher match score actually pay off?
    if len(score_corr) >= 2:
        best = max(score_corr, key=lambda b: b["response_rate"])
        worst = min(score_corr, key=lambda b: b["response_rate"])
        if best["response_rate"] > worst["response_rate"] and best["bucket"] != worst["bucket"]:
            insights.append(
                f"Your reply rate is {best['response_rate']}% on '{best['bucket']}' "
                f"matches vs {worst['response_rate']}% on '{worst['bucket']}'. "
                "Spend your energy on the higher-match roles."
            )

    if _effect_is_positive(tailoring):
        insights.append(
            f"Tailored applications reply at {tailoring['with']['response_rate']}% "
            f"vs {tailoring['without']['response_rate']}% untailored"
            f"{_lift_phrase(tailoring)}. Tailor before every serious application."
        )

    if _effect_is_positive(outreach):
        insights.append(
            f"When you message a recruiter, your reply rate is "
            f"{outreach['with']['response_rate']}% vs "
            f"{outreach['without']['response_rate']}% without outreach"
            f"{_lift_phrase(outreach)}. Reach out every time."
        )

    if funnel["applied"] >= 10 and funnel["response_rate"] < 10:
        insights.append(
            f"A {funnel['response_rate']}% response rate across {funnel['applied']} "
            "applications is low — the bottleneck is likely match quality or resume "
            "tailoring, not volume. Slow down and target better."
        )

    if not insights:
        insights.append("Not enough signal yet to spot a clear pattern — keep logging applications.")
    return insights


def run_autopsy(records: List[dict]) -> dict:
    """
    Analyse application history. Returns funnel metrics, correlations, and
    plain-language insights. Always returns a complete dict; empty input is fine.
    """
    records = records or []
    n = len(records)
    if n == 0:
        return {
            "total_applications": 0,
            "funnel": _funnel([]),
            "score_correlation": [],
            "tailoring_effect": {},
            "outreach_effect": {},
            "insights": ["No applications logged yet. Once you start applying, this "
                         "is where you'll see what's working."],
        }

    funnel = _funnel(records)
    score_corr = _score_correlation(records)
    tailoring = _split_rate(records, lambda r: bool(r.get("tailored")),
                            "tailored", "not tailored")
    outreach = _split_rate(records, lambda r: bool(r.get("outreach_sent")),
                          "with outreach", "no outreach")

    return {
        "total_applications": n,
        "funnel": funnel,
        "score_correlation": score_corr,
        "tailoring_effect": tailoring,
        "outreach_effect": outreach,
        "insights": _insights(funnel, score_corr, tailoring, outreach, n),
    }


# ── Smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    demo = [
        {"company": "Stripe", "match_score": 82, "tailored": True, "outreach_sent": True, "status": "interview"},
        {"company": "Airbnb", "match_score": 74, "tailored": True, "outreach_sent": False, "status": "replied"},
        {"company": "Acme", "match_score": 41, "tailored": False, "outreach_sent": False, "status": "rejected"},
        {"company": "Globex", "match_score": 38, "tailored": False, "outreach_sent": False, "status": "applied"},
        {"company": "Initech", "match_score": 67, "tailored": True, "outreach_sent": True, "status": "replied"},
        {"company": "Umbrella", "match_score": 45, "tailored": False, "outreach_sent": False, "status": "applied"},
    ]
    print(json.dumps(run_autopsy(demo), indent=2))
