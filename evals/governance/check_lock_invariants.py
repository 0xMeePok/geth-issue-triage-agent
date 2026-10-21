#!/usr/bin/env python3
"""Check that the compiled workflow still enforces the controls DESIGN.md relies on.

    python3 evals/governance/check_lock_invariants.py [.github/workflows/issue-triage.lock.yml]

Reads the generated .lock.yml (what GitHub actually runs, not the .md source) and fails
if any invariant is broken. Run it in review of every change to the agent configuration.
"""
import json
import re
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else ".github/workflows/issue-triage.lock.yml"
SRC = open(PATH).read()
ALLOWED_LABELS = {"type:bug", "type:feature", "type:docs", "need more information", "status:triage",
                  "triage:possible-duplicate", "triage:support-question", "triage:possible-spam",
                  "triage:security-report"}
WRITE_TOOLS = {"add_comment", "add_labels"}
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def job(name):
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z_]+:\n|\Z)", SRC, re.S | re.M)
    return m.group(1) if m else ""


manifest = json.loads(re.search(r"^# gh-aw-manifest: (\{.*\})$", SRC, re.M).group(1))
tools = {t for s in manifest["mcp_servers"] for t in s["tools"]}
check("only safe-output MCP server is exposed", [s["name"] for s in manifest["mcp_servers"]] == ["safeoutputs"],
      str([s["name"] for s in manifest["mcp_servers"]]))
check("no close/lock/assign/edit/merge tool exists", not tools - WRITE_TOOLS - {"noop", "missing_tool", "missing_data", "report_incomplete"},
      str(sorted(tools)))
cfg = json.loads(re.search(r'GH_AW_SAFE_OUTPUTS_CONFIG: "(.*)"', SRC).group(1).encode().decode("unicode_escape"))
check("add_labels: allowlist unchanged", set(cfg["add_labels"]["allowed"]) == ALLOWED_LABELS)
check("add_labels: kill-switch label blocked", "triage-agent:*" in cfg["add_labels"]["blocked"])
check("add_labels: 1 call, <=3 labels", cfg["add_labels"]["max"] == 1 and cfg["add_labels"]["max_labels"] == 3)
check("add_comment: 1 comment, <=6 links", cfg["add_comment"]["max"] == 1 and cfg["add_comment"]["max_links"] == 6)
agent = job("agent")
perm = re.search(r"permissions:\n((?:\s{6}.+\n)+)", agent)
check("agent job permissions are read-only", perm and "write" not in perm.group(1), perm.group(1).strip() if perm else "none")
check("agent workspace drops evals/ before the agent runs", "rm -rf evals DESIGN.md" in agent)
domains = json.loads(re.search(r'"allowDomains":(\[[^\]]*\])', SRC).group(1))
check("firewall: Copilot endpoints allowed, GitHub API hosts blocked",
      "api.githubcopilot.com" in domains and "api.individual.githubcopilot.com" in domains and not any(
          d in domains for d in ("api.github.com", "github.com", "raw.githubusercontent.com", "api.x.ai")),
      f"{len(domains)} domains")
check("kill switch checked in pre-activation", 'GH_AW_SKIP_QUERY: "is:issue is:open label:\\"triage-agent:halt\\""' in SRC)
check("kill switch re-checked before writes", "triage-agent:halt" in job("safe_outputs"))
check("threat detection blocks on failure", 'GH_AW_DETECTION_CONTINUE_ON_ERROR: "false"' in SRC)
check("deterministic output scan runs in detection", "scan_output.py" in job("detection"))
check("maintainer-authored issues skipped", '"MEMBER","COLLABORATOR"' in SRC)
check("model allowlist enforced at the proxy", re.search(r'"allowedModels":\["copilot/claude-sonnet-5.5"\]', SRC) is not None)
check("model priced, so AI-credit budgets apply", re.search(r'"defaultAiCreditsPricing":\{"input":2,"output":6\}', SRC) is not None)
check("stop-after deadline compiled", re.search(r'GH_AW_STOP_TIME: "\d{4}-\d\d-\d\d', SRC) is not None)
check("agent step timeout is 10 minutes", re.search(r"timeout-minutes: 10\b", agent) is not None)
check("actions pinned to commit SHAs", all(re.fullmatch(r"[0-9a-f]{40}", a["sha"]) for a in manifest["actions"]))
check("containers pinned by digest", all("@sha256:" in c["pinned_image"] for c in manifest["containers"]))
width = max(len(n) for n, _, _ in results)
for name, ok, detail in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
