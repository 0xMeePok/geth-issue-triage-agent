#!/usr/bin/env python3
"""Deterministic threat detection for the agent's proposed safe outputs.

    python3 scan_output.py /tmp/gh-aw/threat-detection/agent_output.json \
        [--verdict /tmp/gh-aw/threat-detection/detection_result.json]

Runs in the workflow's threat-detection job, after the agent finishes and before anything
is written. A non-zero exit fails detection, and the safe_outputs job is then skipped. It
rejects:
  * output types other than add_labels, add_comment, noop, missing_tool, missing_data,
    report_incomplete
  * labels outside the agent allowlist, more than one add_labels call or more than 3 labels
  * more than one comment, or a comment that is not an unmodified render_comment.py
    template (it must start with the template header and match one template signature)
  * links outside the allowlisted domains, @mentions, and anything that looks like a
    credential (GitHub, xAI, OpenAI, AWS or private-key patterns)
This replaces gh-aw's AI detector, which for the Pi engine needs a Copilot credential the
sandbox does not have. With --verdict it also writes the verdict file gh-aw's "Conclude
threat detection" step requires ({"prompt_injection", "secret_leak", "malicious_patch",
"reasons"}); without that file detection fails closed even when the output is clean.
The workflow's safe-outputs limits still apply independently.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY = json.load(open(os.path.join(HERE, "..", "references", "labels.json")))
ALLOWED_TYPES = {"add_labels", "add_comment", "noop", "missing_tool", "missing_data", "report_incomplete"}
HEADER = "**Automated triage note**"
SIGNATURES = ["A maintainer will need a bit more information", "usage or setup question",
              "may be the same problem as", "an earlier issue reported something similar",
              "handles vulnerabilities privately"]
DOMAINS = {"github.com", "geth.ethereum.org", "discord.gg", "ethereum.stackexchange.com", "bounty.ethereum.org"}
SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xai-[A-Za-z0-9]{20,}|"
                    r"sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                    r"\b[A-Z][A-Z0-9_]*(TOKEN|SECRET|API_KEY)=\S+)")


def label_names(item):
    return [l if isinstance(l, str) else l.get("name", "") for l in item.get("labels", [])]


def scan(items):
    problems = []
    types = [i.get("type") for i in items]
    for t in types:
        if t not in ALLOWED_TYPES:
            problems.append(f"output type not allowed: {t}")
    adds = [i for i in items if i.get("type") == "add_labels"]
    if len(adds) > 1:
        problems.append("more than one add_labels call")
    labels = [l for i in adds for l in label_names(i)]
    for l in labels:
        if l not in POLICY["agent"]:
            problems.append(f"label not allowlisted: {l!r}")
    if len(labels) > POLICY["rules"]["max_labels_per_issue_run"]:
        problems.append(f"too many labels: {len(labels)}")
    comments = [i for i in items if i.get("type") == "add_comment"]
    if len(comments) > 1:
        problems.append("more than one comment")
    texts = [i.get("body", "") for i in comments] + [i.get("message", "") for i in items if i.get("type") == "noop"]
    for c in comments:
        body = c.get("body", "")
        if not body.startswith(HEADER) or not any(s in body for s in SIGNATURES):
            problems.append("comment is not an unmodified render_comment.py template")
        if len(body) > 2500:
            problems.append("comment longer than any template")
    for text in texts:
        for d in re.findall(r"https?://([^/\s)>\]]+)", text):
            if d.lower() not in DOMAINS:
                problems.append(f"link to non-allowlisted domain: {d}")
        if re.search(r"(?<![\w`])@[A-Za-z0-9][A-Za-z0-9-]{0,38}\b", text):
            problems.append("@mention in output")
        if SECRET.search(text):
            problems.append("credential-like string in output")
    return problems


def main():
    args = sys.argv[1:]
    verdict = None
    if "--verdict" in args:
        k = args.index("--verdict")
        verdict = args[k + 1]
        del args[k:k + 2]
    data = json.load(open(args[0]))
    items = data.get("items", data) if isinstance(data, dict) else data
    problems = scan(items)
    print(json.dumps({"items": [i.get("type") for i in items], "problems": problems}, indent=1))
    if verdict:
        leak = [p for p in problems if "credential" in p]
        json.dump({"prompt_injection": len(problems) > len(leak), "secret_leak": bool(leak),
                   "malicious_patch": False, "reasons": problems}, open(verdict, "w"))
    if problems:
        print("THREAT DETECTED: " + "; ".join(problems), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
