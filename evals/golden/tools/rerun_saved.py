#!/usr/bin/env python3
"""Re-run saved golden inputs through the Cursor agent, to measure variance.

Uses the issue, corpus and label files already written for a previous dry run, so the
model sees the same repository state as that run. It does not rebuild the timeline and
it does not change expected.json.

    python3 evals/golden/tools/rerun_saved.py \
        --from evals/golden/runs/2026-10-21-cursor-dryrun \
        --run-dir evals/golden/runs/2026-10-21-holdout-rerun \
        --only H16,H17,H18 \
        --ws-root /path/to/scratch
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dryrun_cursor as dry  # noqa: E402


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="source", required=True, help="run dir whose outputs/<case>/ are replayed")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--only", required=True, help="comma-separated case ids, e.g. H16,H17,H18")
    ap.add_argument("--model", default="grok-4.7-xhigh-fast")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--ws-root", required=True)
    a = ap.parse_args()
    source = os.path.abspath(a.source)
    run_dir = os.path.abspath(a.run_dir)
    cases = [c for c in a.only.split(",") if c]
    for sub in ("actual", "transcripts", "outputs"):
        os.makedirs(os.path.join(run_dir, sub), exist_ok=True)
    shutil.copy(os.path.join(source, "map.json"), os.path.join(run_dir, "map.json"))
    ws = os.path.join(os.path.abspath(a.ws_root), "ws")
    tri = dry.build_workspace(ws)
    dry.install_mcp(ws, os.path.abspath(a.ws_root))
    system = open(os.path.join(dry.DRY, "prompt_system.txt")).read().replace(
        "{AGENT_TMP}", os.path.join(ws, ".gh-aw", "agent-tmp"))
    user_t = open(os.path.join(dry.DRY, "prompt_user.txt")).read().replace("/tmp/gh-aw/triage", tri)
    kinds = {"need-info": "A maintainer will need a bit more information", "support": "usage or setup question",
             "duplicate": "may be the same problem as", "related": "an earlier issue reported something similar",
             "security": "handles vulnerabilities privately"}
    runs = {}
    for ref in cases:
        saved = os.path.join(source, "outputs", ref)
        issue = json.load(open(os.path.join(saved, "issue.json")))
        n = issue["number"]
        out = os.path.join(run_dir, "outputs", ref)
        shutil.rmtree(out, ignore_errors=True)
        os.makedirs(out)
        for name in ("issue.json", "corpus.json", "labels.json"):
            shutil.copy(os.path.join(saved, name), os.path.join(tri, name))
            shutil.copy(os.path.join(saved, name), os.path.join(out, name))
        dry.write_mcp(os.path.abspath(a.ws_root), tri, n, out)
        open(os.path.join(out, "agent_output.jsonl"), "w").close()
        prompt = system + user_t.replace("{ISSUE}", str(n)).replace("{REPO}", dry.REPO)
        open(os.path.join(out, "prompt.txt"), "w").write(prompt)
        started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        code, secs = dry.run_agent(a.model, ws, prompt, os.path.join(run_dir, "transcripts", f"{ref}.jsonl"), a.timeout)
        items = [json.loads(line) for line in open(os.path.join(out, "agent_output.jsonl")) if line.strip()]
        json.dump({"items": items}, open(os.path.join(out, "agent_output.json"), "w"), indent=1, ensure_ascii=False)
        scan = subprocess.run([sys.executable, os.path.join(dry.SKILL, "scripts", "scan_output.py"),
                               os.path.join(out, "agent_output.json")], capture_output=True, text=True)
        open(os.path.join(out, "detection.txt"), "w").write(scan.stdout + scan.stderr)
        agent_ok = code == 0 and any(i["type"] in ("add_labels", "add_comment", "noop") for i in items)
        detection_ok = scan.returncode == 0
        applied = agent_ok and detection_ok
        have = set()
        for lab in issue.get("labels") or []:
            name = lab.get("name") if isinstance(lab, dict) else lab
            if name:
                have.add(name)
        labels_added = [l for i in items if i["type"] == "add_labels" for l in i["labels"] if l not in have] if applied else []
        comments = [i["body"] for i in items if i["type"] == "add_comment"] if applied else []
        summary = dry.summarize_transcript(os.path.join(run_dir, "transcripts", f"{ref}.jsonl"))
        actual = {"ref": ref, "issue": n, "run_id": f"rerun-{ref}", "run_url": f"transcripts/{ref}.jsonl",
                  "conclusion": "success" if applied else "failure",
                  "jobs": {"agent": "success" if agent_ok else f"failure ({code})",
                           "detection": "success" if detection_ok else "failure",
                           "safe_outputs": "success" if applied else "skipped"},
                  "labels_added": sorted(labels_added), "comments": comments,
                  "comment_kinds": [next((k for k, s in kinds.items() if s in c), "free-text") for c in comments],
                  "comment_refs": sorted({int(x) for c in comments for x in re.findall(r"#(\d+)", c)}),
                  "other_bot_events": [], "proposed_items": items, "model": a.model,
                  "transcript_model": summary["model"], "usage": summary["usage"],
                  "started": started, "seconds": secs,
                  "replayed_from": os.path.relpath(saved, dry.ROOT)}
        json.dump(actual, open(os.path.join(run_dir, "actual", f"{ref}.json"), "w"), indent=1, ensure_ascii=False)
        runs[ref] = {"issue": n, "run_id": actual["run_id"], "status": "completed", "conclusion": actual["conclusion"]}
        print(f"{ref} #{n}: exit={code} {secs}s labels={labels_added} comments={actual['comment_kinds']} "
              f"detection={'ok' if detection_ok else 'BLOCKED'}", flush=True)
    json.dump(runs, open(os.path.join(run_dir, "runs.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
