#!/usr/bin/env python3
"""Compute the triage-need metrics reported in metrics/README.md and DESIGN.md.

Usage:
    python3 evals/metrics/compute_metrics.py            # reads evals/metrics/data/issues_window.json

Writes evals/metrics/data/metrics.json and prints a summary. Standard library only.

Definitions (see metrics/README.md for the limitations of each):
  maintainer       login with MEMBER/OWNER/COLLABORATOR association on any comment or
                   issue in the window, every handle in upstream .github/CODEOWNERS, and
                   anyone who labelled, assigned or closed an issue they did not author
                   (GitHub only allows that with triage permission or higher).
  first response   earliest comment, label, assignment or close by a maintainer who is not
                   the issue author. Template labels applied by the author do not count.
  TTFR             first response time minus issue creation time.
"""
import collections
import datetime as dt
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# Handles from ethereum/go-ethereum .github/CODEOWNERS at master 7c50690 (2026-10-20).
CODEOWNERS = {"gballet", "MariusVanDerWijden", "lightclient", "fjl", "zsfelfoldi",
              "rjl493456442", "jwasinger"}
TRUSTED = {"MEMBER", "OWNER", "COLLABORATOR"}
TEMPLATE_LABELS = {"type:bug", "type:feature", "type:docs"}


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def login(node):
    return (node or {}).get("login")


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main():
    d = json.load(open(os.path.join(DATA, "issues_window.json")))
    collected = ts(open(os.path.join(DATA, "collected_at.txt")).read().strip())
    issues = d["issues"]

    maint = set(CODEOWNERS)
    for i in issues:
        if i["authorAssociation"] in TRUSTED:
            maint.add(login(i["author"]))
        for e in i["timelineItems"]["nodes"]:
            if e["__typename"] == "IssueComment" and e["authorAssociation"] in TRUSTED:
                maint.add(login(e["author"]))
        for e in i["timelineItems"]["nodes"]:
            if e["__typename"] in ("LabeledEvent", "AssignedEvent", "ClosedEvent",
                                   "MarkedAsDuplicateEvent"):
                if login(e.get("actor")) != login(i["author"]):
                    maint.add(login(e.get("actor")))
    maint.discard(None)

    rows = []
    for i in issues:
        author = login(i["author"])
        created = ts(i["createdAt"])
        events = sorted(i["timelineItems"]["nodes"], key=lambda e: e["createdAt"])
        first_any = first_maint = None
        maint_labels, kinds = set(), []
        for e in events:
            t = e["__typename"]
            actor = login(e.get("author") if t == "IssueComment" else e.get("actor"))
            if actor is None or actor == author:
                continue
            if t == "IssueComment" and first_any is None:
                first_any = ts(e["createdAt"])
            if actor in maint and t in ("IssueComment", "LabeledEvent", "ClosedEvent",
                                        "AssignedEvent", "MarkedAsDuplicateEvent"):
                if first_maint is None:
                    first_maint = ts(e["createdAt"])
                    kinds.append(t)
                if t == "LabeledEvent":
                    maint_labels.add(e["label"]["name"])
        closed_by = [login(e["actor"]) for e in events if e["__typename"] == "ClosedEvent"]
        rows.append({
            "number": i["number"], "created": i["createdAt"], "assoc": i["authorAssociation"],
            "author_is_maintainer": author in maint,
            "state": i["state"], "reason": i["stateReason"],
            "template_label": sorted({l["name"] for l in i["labels"]["nodes"]} & TEMPLATE_LABELS),
            "labels_now": sorted(l["name"] for l in i["labels"]["nodes"]),
            "maint_labels": sorted(maint_labels),
            "ttfr_h": (first_maint - created).total_seconds() / 3600 if first_maint else None,
            "ttfa_h": (first_any - created).total_seconds() / 3600 if first_any else None,
            "first_kind": kinds[0] if kinds else None,
            "age_h": (collected - created).total_seconds() / 3600,
            "closed_by_author": bool(closed_by) and closed_by[-1] == author,
            "body_len": len(i["body"] or ""),
        })

    ext = [r for r in rows if not r["author_is_maintainer"]]
    resp = [r["ttfr_h"] for r in ext if r["ttfr_h"] is not None]

    def within(hours):
        eligible = [r for r in ext if r["age_h"] >= hours]
        hit = [r for r in eligible if r["ttfr_h"] is not None and r["ttfr_h"] <= hours]
        return {"eligible": len(eligible), "responded": len(hit),
                "share": round(len(hit) / len(eligible), 3) if eligible else None}

    open_unanswered = [r for r in ext if r["state"] == "OPEN" and r["ttfr_h"] is None]
    labelled_by_maint = [r for r in ext if r["maint_labels"]]
    out = {
        "window": [d["since"], d["until"]], "collected_at": collected.isoformat(),
        "issues_total": len(rows), "issues_by_external_authors": len(ext),
        "maintainers_identified": sorted(maint),
        "author_association": dict(collections.Counter(r["assoc"] for r in rows)),
        "ttfr_hours_external": {
            "n_responded": len(resp),
            "median": round(statistics.median(resp), 1) if resp else None,
            "p75": round(pct(resp, .75), 1), "p90": round(pct(resp, .90), 1)},
        "responded_within": {"24h": within(24), "72h": within(72), "7d": within(168),
                             "30d": within(720)},
        "never_responded_external": sum(1 for r in ext if r["ttfr_h"] is None),
        "open_unanswered_external": len(open_unanswered),
        "open_unanswered_older_than_30d": sum(1 for r in open_unanswered if r["age_h"] > 720),
        "first_response_kind": dict(collections.Counter(r["first_kind"] for r in ext)),
        "template_label_share": round(sum(1 for r in rows if r["template_label"]) / len(rows), 3),
        "no_label_at_all": sum(1 for r in rows if not r["labels_now"]),
        "external_with_maintainer_label": len(labelled_by_maint),
        "maintainer_label_names": dict(collections.Counter(
            l for r in labelled_by_maint for l in r["maint_labels"])),
        "state_reason": dict(collections.Counter(f'{r["state"]}/{r["reason"]}' for r in rows)),
        "closed_by_author_external": sum(1 for r in ext if r["closed_by_author"]),
        "silent_close_first_external": sum(1 for r in ext if r["first_kind"] == "ClosedEvent"),
        "per_week_mean": round(len(rows) / 52.1, 1),
        "per_week_max": max(collections.Counter(
            ts(r["created"]).strftime("%G-W%V") for r in rows).values()),
    }
    json.dump({"summary": out, "rows": rows}, open(os.path.join(DATA, "metrics.json"), "w"),
              indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
