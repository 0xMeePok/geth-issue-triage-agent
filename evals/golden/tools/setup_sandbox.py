#!/usr/bin/env python3
"""Create the labels the sandbox needs (idempotent).

    python3 evals/golden/tools/setup_sandbox.py --repo OWNER/REPO

Copies every label from upstream go-ethereum (same name, colour, description) and adds
the agent's triage:* labels plus the human-only kill switch from
.claude/skills/geth-issue-triage/references/labels.json.
"""
import argparse
import json
import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
POLICY = json.load(open(os.path.join(ROOT, ".claude/skills/geth-issue-triage/references/labels.json")))


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    up = json.loads(gh("label", "list", "-R", "ethereum/go-ethereum", "--limit", "200",
                       "--json", "name,color,description").stdout)
    want = {l["name"]: (l["color"], l["description"] or "") for l in up}
    for name, meta in {**POLICY["agent"], **POLICY["human_only"]}.items():
        if name not in want:
            want[name] = (meta.get("color", "ededed"), meta.get("description", ""))
    have = {l["name"] for l in json.loads(gh("label", "list", "-R", a.repo, "--limit", "200",
                                             "--json", "name").stdout)}
    for name, (color, desc) in sorted(want.items()):
        r = gh("label", "create", name, "-R", a.repo, "--color", color, "--description", desc[:100], "--force")
        print(("updated" if name in have else "created"), name, "" if r.returncode == 0 else r.stderr.strip())


if __name__ == "__main__":
    main()
