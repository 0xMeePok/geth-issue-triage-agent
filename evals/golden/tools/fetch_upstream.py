#!/usr/bin/env python3
"""Fetch upstream go-ethereum issues with their ORIGINAL title/body and later history.

Usage: python3 evals/golden/tools/fetch_upstream.py OUT.json NUMBER [NUMBER ...]

For every issue it records:
  original_body   body as first submitted (from userContentEdits when the issue was edited)
  history         comments / labels / close events, kept ONLY as ground truth for
                  expected outcomes; never shown to the agent.
"""
import json, subprocess, sys

Q = """query($n:Int!){ repository(owner:"ethereum", name:"go-ethereum"){ issue(number:$n){
  number title body createdAt closedAt state stateReason authorAssociation url
  author{login} labels(first:20){nodes{name}}
  userContentEdits(first:50){ nodes{ createdAt editedAt diff } }
  timelineItems(first:60, itemTypes:[ISSUE_COMMENT,LABELED_EVENT,UNLABELED_EVENT,CLOSED_EVENT,
      MARKED_AS_DUPLICATE_EVENT,RENAMED_TITLE_EVENT,CROSS_REFERENCED_EVENT]){ nodes{ __typename
    ... on IssueComment{ createdAt authorAssociation author{login} body }
    ... on LabeledEvent{ createdAt label{name} actor{login} }
    ... on UnlabeledEvent{ createdAt label{name} actor{login} }
    ... on ClosedEvent{ createdAt stateReason actor{login}
        closer{ __typename ... on PullRequest{number} ... on Commit{oid} } }
    ... on MarkedAsDuplicateEvent{ createdAt canonical{ ... on Issue{number} } }
    ... on RenamedTitleEvent{ createdAt previousTitle currentTitle }
    ... on CrossReferencedEvent{ createdAt source{ __typename ... on Issue{number title} ... on PullRequest{number title} } }
  } } } } }"""

def fetch(n):
    r = subprocess.run(["gh", "api", "graphql", "-f", "query=" + Q, "-F", f"n={n}"],
                       capture_output=True, text=True, check=True)
    i = json.loads(r.stdout)["data"]["repository"]["issue"]
    edits = sorted(i.pop("userContentEdits")["nodes"], key=lambda e: e["createdAt"])
    # The oldest edit entry holds the text as originally submitted.
    i["original_body"] = edits[0]["diff"] if edits else i["body"]
    i["body_was_edited"] = len(edits) > 1
    renames = [e for e in i["timelineItems"]["nodes"] if e["__typename"] == "RenamedTitleEvent"]
    i["original_title"] = renames[0]["previousTitle"] if renames else i["title"]
    return i

out, nums = sys.argv[1], [int(x) for x in sys.argv[2:]]
json.dump([fetch(n) for n in nums], open(out, "w"), indent=1)
print(f"wrote {len(nums)} issues to {out}")
