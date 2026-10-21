#!/usr/bin/env python3
"""Check a proposed label set against the skill's label policy before calling add_labels.

    python3 validate_labels.py /tmp/gh-aw/triage/issue.json "type:bug,need more information" \
        [--repo-labels /tmp/gh-aw/triage/labels.json]

Rules come from ../references/labels.json:
  * only agent-allowed labels; never human-only labels such as the kill switch
  * at most 3 labels, at most one per group (one type:*, one triage:*)
  * triage:possible-spam stands alone
  * never add a type:* label when the issue already has one
  * labels already on the issue are dropped; every label must exist in the repository
Exit code 0 and {"ok": true, "labels": [...]} when the set is valid, else exit 1 with errors.
The workflow's safe-outputs allowlist enforces the hard limit independently of this script.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY = json.load(open(os.path.join(HERE, "..", "references", "labels.json")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("issue")
    ap.add_argument("labels", help="comma-separated label names")
    ap.add_argument("--repo-labels", default="/tmp/gh-aw/triage/labels.json")
    a = ap.parse_args()
    issue = json.load(open(a.issue))
    present = set(issue.get("labels", []))
    proposed = [l.strip() for l in a.labels.split(",") if l.strip()]
    agent, rules = POLICY["agent"], POLICY["rules"]
    errors, warnings = [], []

    for l in proposed:
        if l in POLICY["human_only"]:
            errors.append(f"'{l}' is human-only and must never be applied by the agent")
        elif l not in agent:
            errors.append(f"'{l}' is not in the agent allowlist")
    if len(set(proposed)) != len(proposed):
        errors.append("duplicate labels in proposal")
    if len(proposed) > rules["max_labels_per_issue_run"]:
        errors.append(f"at most {rules['max_labels_per_issue_run']} labels per run")
    for group in rules["one_per_group"]:
        members = [l for l in proposed if agent.get(l, {}).get("group") == group]
        if len(members) > 1:
            errors.append(f"more than one '{group}' label: {members}")
    for l in rules["exclusive"]:
        if l in proposed and len(proposed) > 1:
            errors.append(f"'{l}' must be the only label")
    has_type = any(l.startswith("type:") for l in present)
    if rules["never_add_type_if_present"] and has_type:
        extra = [l for l in proposed if l.startswith("type:")]
        if extra:
            errors.append(f"issue already has a type label {sorted(l for l in present if l.startswith('type:'))}; "
                          f"do not add {extra} (use status:triage if the existing type looks wrong)")
    final = [l for l in proposed if l not in present]
    if len(final) < len(proposed):
        warnings.append(f"already present, dropped: {[l for l in proposed if l in present]}")
    if os.path.exists(a.repo_labels):
        existing = set(json.load(open(a.repo_labels)))
        for l in final:
            if l not in existing:
                errors.append(f"'{l}' does not exist in this repository; a maintainer must create it")
    else:
        warnings.append("repository label list not found; existence not checked")
    if not final and not errors:
        warnings.append("nothing left to add: use noop unless a comment is needed")
    out = {"ok": not errors, "labels": final, "errors": errors, "warnings": warnings}
    json.dump(out, sys.stdout, indent=1)
    print()
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
