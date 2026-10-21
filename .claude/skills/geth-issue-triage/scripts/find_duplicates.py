#!/usr/bin/env python3
"""Rank earlier issues by textual similarity to the issue being triaged.

    python3 find_duplicates.py /tmp/gh-aw/triage/issue.json /tmp/gh-aw/triage/corpus.json [--top 5]

Deterministic TF-IDF cosine similarity (title weighted 2x over the body excerpt), with
template boilerplate removed so that two empty bug templates do not look alike. It only
retrieves candidates: whether a candidate really is the same problem is the model's call,
made against the rules in SKILL.md. Prints JSON, best match first.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter

from check_template import strip_boilerplate  # same boilerplate rules as the template check

STOP = set("""a an and are as at be been but by can could did do does for from has have how i if
in into is it its may might my no not of on or our should so than that the their then there these
this to was we were what when where which while who why will with would you your also just only
about after all any because before being both each few more most other some such very can't don't
expected actual behaviour behavior steps reproduce system information backtrace version commit hash
client os windows linux osx develop rationale implementation feature use cases willing ideas please
submit logs text screenshots e.g lighthouse nimbus prysm geth""".split())
TOKEN = re.compile(r"[a-z0-9][a-z0-9_./-]*[a-z0-9]|[a-z0-9]")


def tokens(text):
    out = []
    for t in TOKEN.findall(text.lower()):
        if t in STOP or len(t) < 2 or t.isdigit():
            continue
        out.append(t)
        if "/" in t:  # also index package path components: core/txpool -> core, txpool
            out += [p for p in t.split("/") if p and p not in STOP]
    return out


def doc(issue_like, body_key):
    title = issue_like.get("title", "")
    body = strip_boilerplate((issue_like.get(body_key) or "").replace("\r\n", "\n"))
    return tokens(title) * 2 + tokens(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issue")
    ap.add_argument("corpus")
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    issue = json.load(open(a.issue))
    corpus = json.load(open(a.corpus))["issues"]

    q = Counter(doc(issue, "body"))
    docs = [(c, Counter(doc(c, "body_excerpt"))) for c in corpus]
    n = len(docs) + 1
    df = Counter()
    for _, d in docs:
        df.update(set(d))
    df.update(set(q))
    idf = {t: math.log(n / df[t]) + 1.0 for t in df}

    def vec(c):
        return {t: (1 + math.log(f)) * idf[t] for t, f in c.items()}

    qv = vec(q)
    qn = math.sqrt(sum(v * v for v in qv.values())) or 1.0
    ranked = []
    for c, d in docs:
        dv = vec(d)
        dn = math.sqrt(sum(v * v for v in dv.values())) or 1.0
        dot = sum(qv[t] * dv[t] for t in qv.keys() & dv.keys())
        score = dot / (qn * dn)
        shared = sorted(qv.keys() & dv.keys(), key=lambda t: -qv[t] * dv[t])[:8]
        ranked.append((score, c, shared))
    ranked.sort(key=lambda r: -r[0])
    out = {
        "issue": issue.get("number"),
        "corpus_size": len(corpus),
        "note": "score >= 0.35 is a strong textual match, 0.20-0.35 weak; similarity is not proof of duplication",
        "candidates": [{
            "number": c["number"], "title": c["title"], "state": c["state"],
            "state_reason": c.get("state_reason"), "closed_at": c.get("closed_at"),
            "labels": c.get("labels", []), "score": round(s, 3), "shared_terms": shared,
            "excerpt": (c.get("body_excerpt") or "")[:400],
        } for s, c, shared in ranked[:a.top]],
    }
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
