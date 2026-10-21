#!/usr/bin/env python3
"""Collect the data the triage skill needs, before the agent starts.

Runs in the workflow's `steps:` hook on the Actions runner, OUTSIDE the agent sandbox,
with the job's read-only GITHUB_TOKEN. The agent itself has no GitHub token and no
GitHub tools; it only reads the files written here.

    python3 collect_context.py --repo OWNER/REPO --issue N --out /tmp/gh-aw/triage

Writes:
    issue.json   the issue as it is now (title, body, labels, author association, dates)
    corpus.json  earlier issues of the same repository: the 300 most recent plus up to
                 30 keyword-search hits, excluding the issue itself and anything created
                 after it (so replays never see later issues)
    labels.json  names of the labels that exist in the repository

Everything in these files is untrusted user content. Standard library + gh CLI only.
"""
import argparse
import json
import os
import re
import subprocess
import sys

BODY_EXCERPT = 1200
RECENT_LIMIT = 300
STOP = set("""a an and are as at be been but by can could did do does for from has have how
i if in into is it its may might my no not of on or our should so than that the their then
there these this to was we were what when where which while who why will with would you your
geth go ethereum issue bug error fails failed failing support please when""".split())


def gh_api(path, paginate=False):
    args = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        args[2:2] = ["--paginate", "--slurp"]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gh api {path} failed: {r.stderr.strip()[:300]}")
    data = json.loads(r.stdout or "null")
    return [x for page in data for x in page] if paginate else data


def slim(issue):
    return {
        "number": issue["number"],
        "title": issue["title"],
        "state": issue["state"],
        "state_reason": issue.get("state_reason"),
        "labels": sorted(l["name"] for l in issue.get("labels", [])),
        "created_at": issue["created_at"],
        "closed_at": issue.get("closed_at"),
        "body_excerpt": (issue.get("body") or "")[:BODY_EXCERPT],
    }


def keywords(title, k=6):
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.\-/]{2,}", title.lower())
    seen = []
    for w in words:
        if w not in STOP and w not in seen:
            seen.append(w)
    return seen[:k]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--issue", required=True, type=int)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)

    raw = gh_api(f"repos/{a.repo}/issues/{a.issue}")
    if "pull_request" in raw:
        sys.exit("refusing to triage a pull request")
    issue = {
        "repo": a.repo,
        "number": raw["number"],
        "title": raw["title"],
        "body": raw.get("body") or "",
        "labels": sorted(l["name"] for l in raw.get("labels", [])),
        "author": (raw.get("user") or {}).get("login"),
        "author_association": raw.get("author_association"),
        "created_at": raw["created_at"],
        "state": raw["state"],
        "comments": raw.get("comments", 0),
    }

    pages = (RECENT_LIMIT + 99) // 100
    recent = []
    for page in range(1, pages + 1):
        batch = gh_api(f"repos/{a.repo}/issues?state=all&sort=created&direction=desc"
                       f"&per_page=100&page={page}")
        recent += batch
        if len(batch) < 100:
            break
    found = {}
    for it in recent:
        found[it["number"]] = it
    terms = keywords(issue["title"])
    if terms:
        q = " ".join(terms[:4]) + f" repo:{a.repo} is:issue"
        res = subprocess.run(["gh", "api", "-X", "GET", "search/issues", "-f", f"q={q}",
                              "-f", "per_page=30"], capture_output=True, text=True)
        if res.returncode == 0:
            for it in json.loads(res.stdout).get("items", []):
                found.setdefault(it["number"], it)
    corpus = [slim(it) for n, it in sorted(found.items(), reverse=True)
              if "pull_request" not in it and n != issue["number"]
              and it["created_at"] < issue["created_at"]]

    labels = gh_api(f"repos/{a.repo}/labels?per_page=100", paginate=True)

    json.dump(issue, open(os.path.join(a.out, "issue.json"), "w"), indent=1)
    json.dump({"generated_for": issue["number"], "search_terms": terms, "issues": corpus},
              open(os.path.join(a.out, "corpus.json"), "w"), indent=1)
    json.dump(sorted(l["name"] for l in labels),
              open(os.path.join(a.out, "labels.json"), "w"), indent=1)
    print(f"issue #{issue['number']}: corpus={len(corpus)} labels={len(labels)} terms={terms}")


if __name__ == "__main__":
    main()
