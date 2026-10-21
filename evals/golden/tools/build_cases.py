#!/usr/bin/env python3
"""Build the golden cases and the replay timeline from upstream go-ethereum data.

    python3 evals/golden/tools/build_cases.py          # needs `gh` logged in (read-only)

Inputs:  evals/golden/manifest.json, evals/metrics/data/issues_window.json (seed list)
Outputs: evals/golden/cases/<ID>/input.json         what the sandbox issue will contain
         evals/golden/cases/<ID>/ground_truth.json  what maintainers did later (never shown
                                                    to the agent; used to justify expected.json)
         evals/golden/corpus/seeds.json             earlier issues replayed as background
         evals/golden/corpus/timeline.json          create/close/reopen events in original order
         evals/golden/corpus/raw_upstream.json      raw fetch, for audit

Leakage controls: bodies are the text as ORIGINALLY submitted (from the edit history),
titles are the original titles, and only events before the last case are replayed.
Replay transformations (recorded per case): @mentions neutralised so no real person is
notified, upstream issue links rewritten so no cross-reference is created upstream,
e-mail addresses and phone numbers redacted, and known phishing links defanged.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GOLD = os.path.join(ROOT, "evals", "golden")
ZWSP = "​"
DEFANG = {"https://victim-dev-verify.github.io/verify": "hxxps://victim-dev-verify[.]github[.]io/verify"}

FIELDS = """number title body createdAt closedAt state stateReason authorAssociation url
  author{login} labels(first:20){nodes{name}}
  userContentEdits(first:100){nodes{createdAt diff}}
  timelineItems(first:100, itemTypes:[ISSUE_COMMENT,LABELED_EVENT,CLOSED_EVENT,REOPENED_EVENT,
      RENAMED_TITLE_EVENT,MARKED_AS_DUPLICATE_EVENT]){nodes{__typename
    ... on IssueComment{createdAt authorAssociation author{login} body}
    ... on LabeledEvent{createdAt label{name} actor{login}}
    ... on ClosedEvent{createdAt stateReason actor{login}}
    ... on ReopenedEvent{createdAt actor{login}}
    ... on RenamedTitleEvent{createdAt previousTitle currentTitle}
    ... on MarkedAsDuplicateEvent{createdAt canonical{... on Issue{number}}}}}"""


def fetch(numbers):
    out = {}
    for k in range(0, len(numbers), 15):
        chunk = numbers[k:k + 15]
        q = "query{repository(owner:\"ethereum\",name:\"go-ethereum\"){" + " ".join(
            f"i{n}:issue(number:{n}){{{FIELDS}}}" for n in chunk) + "}}"
        r = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stderr[:500])
        for v in json.loads(r.stdout)["data"]["repository"].values():
            out[v["number"]] = v
        print(f"fetched {len(out)}/{len(numbers)}", file=sys.stderr)
    return out


def original(issue):
    edits = sorted(issue["userContentEdits"]["nodes"], key=lambda e: e["createdAt"])
    body = edits[0]["diff"] if edits else issue["body"]
    ren = [e for e in issue["timelineItems"]["nodes"] if e["__typename"] == "RenamedTitleEvent"]
    title = ren[0]["previousTitle"] if ren else issue["title"]
    return title, body or "", len(edits) > 1, bool(ren)


def transform(text, log):
    def note(kind, n):
        if n:
            log.append(f"{kind}: {n}")
    t, n = re.subn(r"(?<![\w`])@(?=[A-Za-z0-9][A-Za-z0-9-]{0,38}\b)", "@" + ZWSP, text)
    note("mentions neutralised", n)
    t, n = re.subn(r"https?://github\.com/ethereum/go-ethereum/(issues|pull)/(\d+)", r"upstream \1 \2", t)
    note("upstream links rewritten", n)
    t, n = re.subn(r"\bethereum/go-ethereum#(\d+)", r"upstream #\1", t)
    note("upstream refs rewritten", n)
    t, n = re.subn(r"\b[\w.+-]+@(?!ethereum\.org\b)[A-Za-z][\w-]*(\.[A-Za-z][\w-]*)*\.[A-Za-z]{2,}\b",
                   "[email redacted]", t)
    note("emails redacted", n)
    t, n = re.subn(r"\+\d{1,3}[\s-]?\d{6,12}\b", "[phone redacted]", t)
    note("phone numbers redacted", n)
    for bad, safe in DEFANG.items():
        if bad in t:
            t = t.replace(bad, safe)
            log.append(f"phishing link defanged: {safe}")
    return t


def labels_at_creation(issue):
    created, author = issue["createdAt"], (issue["author"] or {}).get("login")
    return sorted({e["label"]["name"] for e in issue["timelineItems"]["nodes"]
                   if e["__typename"] == "LabeledEvent" and (e["actor"] or {}).get("login") == author
                   and e["createdAt"][:16] <= created[:16]})


def ground_truth(issue):
    author = (issue["author"] or {}).get("login")
    acts = []
    for e in sorted(issue["timelineItems"]["nodes"], key=lambda e: e["createdAt"]):
        t = e["__typename"]
        who = ((e.get("author") or e.get("actor")) or {}).get("login")
        if who == author or t == "RenamedTitleEvent":
            continue
        detail = {"IssueComment": lambda: e["body"][:280], "LabeledEvent": lambda: e["label"]["name"],
                  "ClosedEvent": lambda: e["stateReason"], "ReopenedEvent": lambda: "",
                  "MarkedAsDuplicateEvent": lambda: str((e.get("canonical") or {}).get("number"))}[t]()
        acts.append({"at": e["createdAt"], "kind": t, "by": who,
                     "assoc": e.get("authorAssociation"), "detail": detail})
    return {"upstream_url": issue["url"], "final_state": issue["state"], "state_reason": issue["stateReason"],
            "closed_at": issue["closedAt"], "labels_now": sorted(l["name"] for l in issue["labels"]["nodes"]),
            "non_author_actions": acts}


def main():
    man = json.load(open(os.path.join(GOLD, "manifest.json")))
    excluded = {int(k) for k in man["excluded_from_everything"]}
    hist = [c for c in man["cases"] if not c.get("adversarial")]
    case_nums = {c["upstream"] for c in hist}
    win = json.load(open(os.path.join(ROOT, "evals", "metrics", "data", "issues_window.json")))["issues"]
    lo, hi = man["seed_window"]
    seed_nums = sorted(i["number"] for i in win if lo <= i["createdAt"] < hi
                       and i["number"] not in case_nums | excluded)
    raw = fetch(sorted(case_nums) + seed_nums)
    os.makedirs(os.path.join(GOLD, "corpus"), exist_ok=True)
    json.dump(raw, open(os.path.join(GOLD, "corpus", "raw_upstream.json"), "w"), indent=1)

    last_case = max(raw[c["upstream"]]["createdAt"] for c in hist)
    timeline, seeds = [], []
    for c in hist:
        i = raw[c["upstream"]]
        title, body, edited, renamed = original(i)
        log = []
        if edited:
            log.append("body taken from the first revision (issue was edited later)")
        if renamed:
            log.append("original title restored (issue was renamed later)")
        d = os.path.join(GOLD, "cases", c["id"])
        os.makedirs(d, exist_ok=True)
        inp = {"id": c["id"], "set": c["set"], "category": c["category"],
               "upstream_number": i["number"], "upstream_url": i["url"],
               "original_created_at": i["createdAt"],
               "original_author_association": i["authorAssociation"],
               "labels_at_creation": labels_at_creation(i),
               "title": transform(title, log), "body": transform(body, log), "replay_transformations": log}
        json.dump(inp, open(os.path.join(d, "input.json"), "w"), indent=1, ensure_ascii=False)
        json.dump(ground_truth(i), open(os.path.join(d, "ground_truth.json"), "w"), indent=1, ensure_ascii=False)
        timeline.append({"at": i["createdAt"], "op": "create", "ref": c["id"]})
    for n in seed_nums:
        i = raw[n]
        title, body, _, _ = original(i)
        log = []
        seeds.append({"ref": f"S{n}", "upstream_number": n, "original_created_at": i["createdAt"],
                      "labels_at_creation": labels_at_creation(i), "title": transform(title, log),
                      "body": transform(body, log), "replay_transformations": log})
        timeline.append({"at": i["createdAt"], "op": "create", "ref": f"S{n}"})
    for n, i in raw.items():
        ref = next((c["id"] for c in hist if c["upstream"] == n), f"S{n}")
        for e in i["timelineItems"]["nodes"]:
            if e["__typename"] in ("ClosedEvent", "ReopenedEvent") and e["createdAt"] < last_case:
                op = "close" if e["__typename"] == "ClosedEvent" else "reopen"
                timeline.append({"at": e["createdAt"], "op": op, "ref": ref,
                                 "reason": e.get("stateReason")})
    timeline.sort(key=lambda e: (e["at"], e["op"] != "create"))
    json.dump(seeds, open(os.path.join(GOLD, "corpus", "seeds.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(timeline, open(os.path.join(GOLD, "corpus", "timeline.json"), "w"), indent=1)
    print(f"{len(hist)} cases, {len(seeds)} seeds, {len(timeline)} timeline events, last case {last_case}")


if __name__ == "__main__":
    main()
