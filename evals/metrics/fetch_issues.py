#!/usr/bin/env python3
"""Fetch every go-ethereum issue created in a time window, with its timeline.

Usage:
    python3 evals/metrics/fetch_issues.py [--since 2025-10-15] [--until 2026-10-14]

Writes evals/metrics/data/issues_window.json (one object per issue) and
evals/metrics/data/collected_at.txt. Needs the gh CLI, logged in with any account.

Only the standard library is used. GitHub search returns at most 1000 results,
so the window must contain fewer than 1000 issues (it contains about 250).
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

REPO = "ethereum/go-ethereum"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")

QUERY = """
query($q: String!, $cursor: String) {
  search(query: $q, type: ISSUE, first: 25, after: $cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on Issue {
        number title body url createdAt closedAt state stateReason
        authorAssociation
        author { login __typename }
        labels(first: 20) { nodes { name } }
        timelineItems(first: 100, itemTypes: [ISSUE_COMMENT, LABELED_EVENT,
            UNLABELED_EVENT, CLOSED_EVENT, REOPENED_EVENT,
            MARKED_AS_DUPLICATE_EVENT, ASSIGNED_EVENT]) {
          totalCount
          nodes {
            __typename
            ... on IssueComment { createdAt authorAssociation body
                                  author { login __typename } }
            ... on LabeledEvent { createdAt label { name } actor { login __typename } }
            ... on UnlabeledEvent { createdAt label { name } actor { login __typename } }
            ... on ClosedEvent { createdAt stateReason actor { login __typename } }
            ... on ReopenedEvent { createdAt actor { login __typename } }
            ... on MarkedAsDuplicateEvent { createdAt actor { login __typename }
                    canonical { ... on Issue { number } ... on PullRequest { number } } }
            ... on AssignedEvent { createdAt actor { login __typename } }
          }
        }
      }
    }
  }
}
"""


def gh_graphql(variables):
    args = ["gh", "api", "graphql", "-f", "query=" + QUERY]
    for k, v in variables.items():
        if v is not None:
            args += ["-F", f"{k}={v}"]
    for attempt in range(5):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
        sys.stderr.write(f"retry {attempt}: {r.stderr[:300]}\n")
        time.sleep(5 * (attempt + 1))
    raise SystemExit("GraphQL query failed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--since", default="2025-10-15")
    p.add_argument("--until", default="2026-10-14")
    a = p.parse_args()
    q = f"repo:{REPO} is:issue created:{a.since}..{a.until} sort:created-asc"
    issues, cursor = [], None
    while True:
        d = gh_graphql({"q": q, "cursor": cursor})["data"]["search"]
        issues += [n for n in d["nodes"] if n]
        if not d["pageInfo"]["hasNextPage"]:
            break
        cursor = d["pageInfo"]["endCursor"]
    truncated = [i["number"] for i in issues if i["timelineItems"]["totalCount"] > 100]
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "issues_window.json"), "w") as f:
        json.dump({"repo": REPO, "since": a.since, "until": a.until,
                   "issue_count": d["issueCount"], "timeline_truncated": truncated,
                   "issues": issues}, f, indent=1)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    with open(os.path.join(OUT, "collected_at.txt"), "w") as f:
        f.write(now + "\n")
    print(f"{len(issues)} issues (search says {d['issueCount']}), "
          f"timeline truncated for {truncated}, collected {now}")


if __name__ == "__main__":
    main()
