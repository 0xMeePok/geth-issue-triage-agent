#!/usr/bin/env python3
"""Collect what the agent actually did for every replayed case.

    python3 evals/golden/tools/collect_outputs.py --repo OWNER/REPO --run-dir evals/golden/runs/NAME [--audit]

For each case in RUN_DIR/runs.json it writes RUN_DIR/actual/<ID>.json with the labels the
bot added, the comments it posted, every other bot event on the issue (close, lock, assign,
...), the run's job conclusions, and the model and token usage recorded by gh-aw. It also
checks the whole repository for bot writes on issues that are not golden cases
(RUN_DIR/collateral.json). With --audit it saves `gh aw audit` reports under RUN_DIR/logs/.
"""
import argparse
import json
import os
import re
import subprocess

BOT = "github-actions[bot]"
KIND = {"need-info": "A maintainer will need a bit more information", "support": "usage or setup question",
        "duplicate": "may be the same problem as", "related": "an earlier issue reported something similar",
        "security": "handles vulnerabilities privately"}


def gh_json(*args):
    if "--paginate" in args:
        args = (*args, "--slurp")  # one JSON array of pages
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[:300])
    data = json.loads(r.stdout or "null")
    if "--paginate" in args:
        data = [x for page in data for x in page]
    return data


def kind_of(body):
    return next((k for k, sig in KIND.items() if sig in body), "free-text")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--audit", action="store_true")
    a = ap.parse_args()
    runs = json.load(open(os.path.join(a.run_dir, "runs.json")))
    os.makedirs(os.path.join(a.run_dir, "actual"), exist_ok=True)
    case_issues = set()
    for ref, r in sorted(runs.items()):
        n = r["issue"]
        case_issues.add(n)
        tl = gh_json("api", "--paginate", f"repos/{a.repo}/issues/{n}/timeline?per_page=100")
        labels, comments, other = [], [], []
        for e in tl:
            who = (e.get("actor") or e.get("user") or {}).get("login")
            if who != BOT:
                continue
            if e["event"] == "labeled":
                labels.append(e["label"]["name"])
            elif e["event"] == "commented":
                comments.append(e["body"])
            else:
                other.append({"event": e["event"], "at": e.get("created_at")})
        jobs = {}
        try:
            for j in gh_json("run", "view", str(r["run_id"]), "-R", a.repo, "--json", "jobs")["jobs"]:
                jobs[j["name"]] = j["conclusion"] or j["status"]
        except Exception as exc:  # run may have been deleted
            jobs = {"error": str(exc)}
        out = {"ref": ref, "issue": n, "run_id": r.get("run_id"), "run_url": r.get("url"),
               "conclusion": r.get("conclusion"), "jobs": jobs, "labels_added": sorted(labels),
               "comments": comments, "comment_kinds": [kind_of(c) for c in comments],
               "comment_refs": sorted({int(x) for c in comments for x in re.findall(r"#(\d+)", c)}),
               "other_bot_events": other}
        if a.audit and r.get("run_id"):
            d = os.path.join(a.run_dir, "logs", ref)
            os.makedirs(d, exist_ok=True)
            subprocess.run(["gh", "aw", "audit", str(r["run_id"]), "--repo", a.repo, "-o", d, "--parse"],
                           capture_output=True, text=True)
        json.dump(out, open(os.path.join(a.run_dir, "actual", f"{ref}.json"), "w"), indent=1, ensure_ascii=False)
        print(ref, n, out["labels_added"], out["comment_kinds"], out["other_bot_events"] or "")
    events = gh_json("api", "--paginate", f"repos/{a.repo}/issues/events?per_page=100")
    comments = gh_json("api", "--paginate", f"repos/{a.repo}/issues/comments?per_page=100")
    collateral = [{"event": e["event"], "issue": e["issue"]["number"]} for e in events
                  if (e.get("actor") or {}).get("login") == BOT and e["issue"]["number"] not in case_issues]
    collateral += [{"event": "commented", "issue": int(c["issue_url"].rsplit("/", 1)[1])} for c in comments
                   if c["user"]["login"] == BOT and int(c["issue_url"].rsplit("/", 1)[1]) not in case_issues]
    json.dump(collateral, open(os.path.join(a.run_dir, "collateral.json"), "w"), indent=1)
    print("bot writes outside golden cases:", collateral or "none")


if __name__ == "__main__":
    main()
