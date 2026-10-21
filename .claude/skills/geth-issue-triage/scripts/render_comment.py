#!/usr/bin/env python3
"""Render the single comment the agent may post, from fixed templates.

    python3 render_comment.py need-info --missing geth_version,steps [--question "..."]
    python3 render_comment.py support [--reported-version 1.16.0 --repo-version 1.17.4]
    python3 render_comment.py duplicate --candidates 101,87 [--corpus /tmp/gh-aw/triage/corpus.json]
    python3 render_comment.py related --candidates 87 [--corpus ...]
    python3 render_comment.py security

The model chooses the template and its parameters; it does not write the comment. The only
free text is --question (need-info only): one sentence, at most 200 characters, with links,
mentions, issue references, HTML and markdown markup removed. Candidate numbers must exist
in the corpus, so the agent cannot point reporters at arbitrary issues. Output: markdown.
"""
import argparse
import json
import re
import sys

MISSING = {
    "geth_version": "**Geth version**: the full output of `geth version`",
    "os": "**Operating system** and architecture",
    "cl_client": "**Consensus client** and its version (e.g. Lighthouse, Prysm, Teku)",
    "steps": "**Steps to reproduce**: the exact commands, flags or RPC calls you ran",
    "expected_actual": "**Expected vs actual behaviour**: what you expected to happen and what happened instead",
    "logs": "**Logs or backtrace** as text (not screenshots), ideally with `--verbosity 4`",
    "where": "**Where you saw it**: the page, download channel or package repository you used",
}
SUPPORT_LINKS = ("- Geth documentation: https://geth.ethereum.org/docs\n"
                 "- Discord: https://discord.gg/nthXNEv\n"
                 "- Ethereum Stack Exchange: https://ethereum.stackexchange.com")


def clean_question(q):
    q = re.sub(r"<[^>]*>", "", q)
    q = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", q)           # markdown links/images -> text
    q = re.sub(r"(https?://|www\.)\S+", "", q)
    q = re.sub(r"[@#]\S+", "", q)                              # mentions and issue refs
    q = re.sub(r"[`*_~>|]", "", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q[:200]


def candidates(arg, corpus_path):
    nums = [int(x) for x in arg.split(",") if x.strip()][:2]
    corpus = {c["number"]: c for c in json.load(open(corpus_path))["issues"]}
    out = []
    for n in nums:
        if n not in corpus:
            sys.exit(f"#{n} is not in the duplicate-candidate corpus; refusing to reference it")
        c = corpus[n]
        state = "closed" if c["state"] == "closed" else "open"
        title = re.sub(r"[`*_<>\[\]]", "", c["title"])[:120]
        out.append(f"- #{n}: {title} ({state})")
    if not out:
        sys.exit("no candidates given")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["need-info", "support", "duplicate", "related", "security"])
    ap.add_argument("--missing", default="")
    ap.add_argument("--question", default="")
    ap.add_argument("--candidates", default="")
    ap.add_argument("--corpus", default="/tmp/gh-aw/triage/corpus.json")
    ap.add_argument("--reported-version", default="")
    ap.add_argument("--repo-version", default="")
    a = ap.parse_args()

    if a.kind == "need-info":
        keys = [k.strip() for k in a.missing.split(",") if k.strip()]
        bad = [k for k in keys if k not in MISSING]
        if bad or not keys:
            sys.exit(f"--missing must list items from {sorted(MISSING)}; got {keys}")
        body = ("Thanks for the report! A maintainer will need a bit more information to look "
                "into this. Please edit the issue to add:\n\n"
                + "\n".join("- " + MISSING[k] for k in keys))
        q = clean_question(a.question)
        if q:
            body += f"\n\nSpecifically: {q}"
    elif a.kind == "support":
        body = ("Thanks for reaching out! This reads like a usage or setup question rather than a "
                "bug in go-ethereum, and the community channels usually answer those faster:\n\n"
                + SUPPORT_LINKS +
                "\n\nIf you do think this is a bug, please add the details asked for in the bug "
                "report template (Geth version, steps to reproduce, expected and actual behaviour).")
        if re.fullmatch(r"\d+\.\d+\.\d+", a.reported_version) and re.fullmatch(r"\d+\.\d+\.\d+", a.repo_version):
            body += (f"\n\nYou mention Geth {a.reported_version}; development is on "
                     f"{a.repo_version.rsplit('.', 1)[0]}.x, so please also check whether the "
                     "latest release behaves the same.")
    elif a.kind == "duplicate":
        body = ("Thanks for the report! This looks like it may be the same problem as:\n\n"
                + candidates(a.candidates, a.corpus) +
                "\n\nIf it is, please add any new details there. A maintainer will confirm "
                "before anything is closed; if this is a different problem, just say so here.")
    elif a.kind == "related":
        body = ("For reference, an earlier issue reported something similar:\n\n"
                + candidates(a.candidates, a.corpus) +
                "\n\nLinking it in case the history helps the maintainers.")
    else:
        body = ("Thanks for the report. If this describes a security vulnerability, please do not "
                "add exploit details here: go-ethereum handles vulnerabilities privately through "
                "the Ethereum Foundation bug bounty at https://bounty.ethereum.org (or "
                "bounty@ethereum.org), as described in `SECURITY.md`. A maintainer has been "
                "flagged to review this issue.")
    print("**Automated triage note**\n\n" + body)


if __name__ == "__main__":
    main()
