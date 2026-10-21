#!/usr/bin/env python3
"""Deterministic checks on one issue. No model judgement, no network.

    python3 check_template.py /tmp/gh-aw/triage/issue.json [--version-file version/version.go]

Prints JSON with:
  template            bug | feature | question | none   (which upstream template was used)
  user_text_chars     characters the reporter wrote, after removing template boilerplate
  template_untouched  true when the reporter wrote (almost) nothing
  fields              which bug-report facts are present (version, OS, steps, logs, ...)
  missing_for_bug     bug-template facts that are absent (only a hint: the skill decides)
  reported_version / repo_version / minor_versions_behind
  signals             keyword hits for spam, phishing, promotion, support questions,
                      security reports, instructions aimed at the bot, and personal data
The skill uses these as evidence; the decision itself stays with the model.
"""
import argparse
import json
import os
import re
import sys

BOILERPLATE = [
    r"^#+\s*(system information|expected behaviou?r|actual behaviou?r|steps to reproduce( the behaviou?r)?|backtrace|rationale|implementation)\s*$",
    r"^geth version:\s*`geth version`\s*$",
    r"^cl client & version:\s*e\.g\. lighthouse/nimbus/prysm@v1\.0\.0\s*$",
    r"^os & version:\s*windows/linux/osx\s*$",
    r"^commit hash\s*:\s*\(if `develop`\)\s*$",
    r"^`{3,}\s*$", r"^\[backtrace\]$",
    r"^when submitting logs: please submit them as text and not screenshots\.$",
    r"^why should this feature exist\?$", r"^what are the use-cases\?$",
    r"^do you have ideas regarding the implementation of this feature\?$",
    r"^are you willing to implement this feature\?$",
    r"^this should only be used in very rare cases.*stack exchange.*$",
    r"^(geth version|cl client & version|os & version|commit hash)\s*:\s*$",
]
SIGNALS = {
    "security": r"\b(vulnerab\w*|exploit\w*|attacker|denial[- ]of[- ]service|\bdos\b|remote(ly)? crash|cve-\d+|rce\b|code injection|source code injection|unbounded (memory )?allocation|out[- ]of[- ]memory|oom\b|malicious (peer|payload|input)|consensus (split|failure|bug)|security (assessment|audit|finding)|hack-\d+|bypass)",
    "phishing": r"(verify (your )?(account|identity)|verification (page|required)|account restrictions?|token (was )?(exposed|leaked)|within 24 hours|security notification|seed phrase|recover (my |your )?funds|claim (your )?(airdrop|reward)|wallet (drained|connect))",
    "promotion": r"(\bi maintain\b|\bmy (tool|project|startup|product)\b|\bour (tool|product|platform)\b|free hosted|\d+\+ ?👍|check out (my|our)|sponsor(ed)?|giveaway|promo code)",
    "support": r"(\bhow (do|can|to|should) (i|we|you)\b|\btrying to (set up|setup|run|configure|sync)\b|\bprivate (pos |poa )?(chain|network|testnet)\b|\bcan(no|')?t (get|figure|make)\b|\bany (help|advice|clarification)\b|\bis it possible\b|\bwhen will\b)",
    "bot_instructions": r"(ignore (all |any )?(previous|prior|above) instructions|you are (an? )?(ai|bot|assistant|agent)|as the triage (bot|agent)|\bclose (all|every|these|stale)\b|\bdelete (all|this|the) (issues?|labels?|comments?)\b|(maintainers?|admins?) (have |has )?approved|approved by (the )?maintainers|\bsystem prompt\b|\bprint (the )?(env|environment|secrets?)\b|\b(lock|transfer) (all|every|these) issues\b|\badd (the )?label\b|\bassign (this|it) to\b)",
    "pii": r"(\+\d{1,3}[\s-]?\d{6,12}\b|\b[\w.+-]+@(?!ethereum\.org)[\w-]+\.[\w.]+\b)",
}
LOG_LINE = re.compile(r"^(INFO|WARN|ERROR|DEBUG|TRACE|CRIT|FATAL)\s*\[|^panic:|^goroutine \d+|^\s+at |^fatal error:", re.M)


def section(body, name):
    m = re.search(r"^#+\s*" + name + r"[^\n]*\n(.*?)(?=^#+\s|\Z)", body, re.I | re.M | re.S)
    return (m.group(1) if m else "").strip()


def strip_boilerplate(body):
    keep = []
    for line in body.splitlines():
        s = line.strip()
        if s and not any(re.match(p, s, re.I) for p in BOILERPLATE):
            keep.append(s)
    return "\n".join(keep)


def repo_version(path):
    try:
        src = open(path).read()
    except OSError:
        return None
    parts = [re.search(rf"{k}\s*=\s*(\d+)", src) for k in ("Major", "Minor", "Patch")]
    return ".".join(m.group(1) for m in parts) if all(parts) else None


def reported_version(text):
    for pat in (r"geth/v(\d+\.\d+\.\d+)", r"\bversion:\s*v?(\d+\.\d+\.\d+)",
                r"\bgeth\b[^\n0-9]{0,25}v?(\d+\.\d+\.\d+)", r"\bv(1\.1\d\.\d+)\b"):
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issue")
    ap.add_argument("--version-file", default="version/version.go")
    a = ap.parse_args()
    issue = json.load(open(a.issue))
    title, body = issue.get("title", ""), (issue.get("body") or "").replace("\r\n", "\n")
    low = body.lower()

    if re.search(r"^#+\s*(system information|expected behaviou?r)", body, re.I | re.M):
        template = "bug"
    elif re.search(r"^#\s*rationale", body, re.I | re.M) and re.search(r"^#\s*implementation", body, re.I | re.M):
        template = "feature"
    elif "this should only be used in very rare cases" in low:
        template = "question"
    else:
        template = "none"
    user_text = strip_boilerplate(body)
    text = title + "\n" + body

    rep = reported_version(text)
    cur = repo_version(a.version_file)
    behind = None
    if rep and cur and rep.split(".")[0] == cur.split(".")[0]:
        behind = int(cur.split(".")[1]) - int(rep.split(".")[1])

    fields = {
        "geth_version": rep is not None,
        "os": bool(re.search(r"\b(ubuntu|debian|arch linux|fedora|centos|windows|macos|osx|darwin|linux)\b", low)),
        "commit_hash": bool(re.search(r"\b[0-9a-f]{7,40}\b", low) and "commit" in low),
        "cl_client": bool(re.search(r"\b(lighthouse|prysm|nimbus|teku|lodestar|grandine)\b", low)),
        "expected": bool(strip_boilerplate(section(body, "expected behaviou?r"))) or "expected" in low,
        "actual": bool(strip_boilerplate(section(body, "actual behaviou?r"))) or "actual" in low,
        "steps": bool(strip_boilerplate(section(body, "steps to reproduce"))) or bool(
            re.search(r"(steps to reproduce|reproduc\w+|```(sh|bash|shell|console))", low)),
        "logs_or_backtrace": bool(LOG_LINE.search(body)) or bool(re.search(r"```[\s\S]{40,}?```", body)),
        "code_references": bool(re.search(r"\b[\w-]+(/[\w.-]+)+\.go\b|\b(core|eth|p2p|rpc|trie|triedb|miner|internal|beacon|cmd|params|accounts|crypto|ethdb|node)/[\w/]+", body)),
    }
    missing = [k for k in ("geth_version", "steps", "actual") if not fields[k]]
    signals = {}
    for name, pat in SIGNALS.items():
        hits = sorted({m.group(0).strip().lower() for m in re.finditer(pat, text, re.I)})
        if hits:
            signals[name] = hits[:6]
    domains = sorted({d.lower() for d in re.findall(r"https?://([\w.-]+)", text)
                      if not re.search(r"(^|\.)github(usercontent)?\.com$", d.lower())})
    labels = issue.get("labels", [])
    out = {
        "number": issue.get("number"),
        "template": template,
        "user_text_chars": len(re.sub(r"\s", "", user_text)),
        "template_untouched": len(re.sub(r"\s", "", user_text)) < 15,
        "title_words": len(re.findall(r"[A-Za-z]{2,}", title)),
        "fields": fields,
        "missing_for_bug": missing,
        "reported_version": rep,
        "repo_version": cur,
        "minor_versions_behind": behind,
        "signals": signals,
        "external_domains": domains,
        "labels_present": labels,
        "type_label_present": next((l for l in labels if l.startswith("type:")), None),
        "author_association": issue.get("author_association"),
    }
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
