#!/usr/bin/env python3
"""Replay the golden timeline into the sandbox repository, end to end.

    python3 evals/golden/tools/replay_live.py --repo OWNER/REPO --run-dir evals/golden/runs/NAME

Walks evals/golden/corpus/timeline.json in original chronological order, then appends the
adversarial cases. Background issues (seeds) are created while the triage workflow is
DISABLED, so only golden cases trigger the agent. For each case the workflow is enabled,
the issue is opened exactly as originally submitted (labels the upstream template applied
are set at creation), and the script waits for the triggered run to finish before replaying
later events, so every case sees the repository as it was at that moment. Close/reopen
events are replayed by the operator, never by the agent.

State is checkpointed to RUN_DIR/map.json (ref -> sandbox issue) and RUN_DIR/runs.json
(case -> workflow run), so an interrupted replay can be resumed with the same command.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
GOLD = os.path.join(ROOT, "evals", "golden")
WORKFLOW = "issue-triage.lock.yml"


def gh(*args, check=True):
    for attempt in range(4):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0 or not check:
            return r
        if "secondary rate limit" in r.stderr.lower() or "abuse" in r.stderr.lower():
            time.sleep(60 * (attempt + 1))
            continue
        sys.exit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:400]}")
    sys.exit("gave up after rate limiting")


def save(path, obj):
    json.dump(obj, open(path + ".tmp", "w"), indent=1)
    os.replace(path + ".tmp", path)


class Replay:
    def __init__(self, repo, run_dir, only):
        self.repo, self.dir, self.only = repo, run_dir, only
        os.makedirs(run_dir, exist_ok=True)
        self.map_path, self.runs_path = os.path.join(run_dir, "map.json"), os.path.join(run_dir, "runs.json")
        self.map = json.load(open(self.map_path)) if os.path.exists(self.map_path) else {}
        self.runs = json.load(open(self.runs_path)) if os.path.exists(self.runs_path) else {}
        self.enabled = None

    def workflow(self, enable):
        if self.enabled is enable:
            return
        gh("workflow", "enable" if enable else "disable", WORKFLOW, "-R", self.repo)
        self.enabled = enable
        time.sleep(3)

    def create(self, ref, title, body, labels):
        if ref in self.map:
            return self.map[ref]
        args = ["issue", "create", "-R", self.repo, "--title", title, "--body", body or " "]
        for l in labels:
            args += ["--label", l]
        url = gh(*args).stdout.strip().splitlines()[-1]
        self.map[ref] = int(url.rstrip("/").split("/")[-1])
        save(self.map_path, self.map)
        time.sleep(1.5)
        return self.map[ref]

    def wait_run(self, ref, number, opened_at):
        deadline = time.time() + 40 * 60
        run_id = None
        while time.time() < deadline:
            out = gh("run", "list", "-R", self.repo, "--workflow", WORKFLOW, "--event", "issues",
                     "--limit", "20", "--json", "databaseId,createdAt,status,conclusion,displayTitle").stdout
            cands = [r for r in json.loads(out) if r["createdAt"] >= opened_at]
            if run_id is None and cands:
                # the oldest run created after this issue was opened belongs to it
                run_id = sorted(cands, key=lambda r: r["createdAt"])[0]["databaseId"]
                print(f"  {ref}: issue #{number} -> run {run_id}")
            if run_id:
                r = json.loads(gh("run", "view", str(run_id), "-R", self.repo, "--json",
                                  "status,conclusion,createdAt,updatedAt,url").stdout)
                if r["status"] == "completed":
                    self.runs[ref] = {"issue": number, "run_id": run_id, **r}
                    save(self.runs_path, self.runs)
                    print(f"  {ref}: {r['conclusion']} {r['url']}")
                    return
            time.sleep(20)
        self.runs[ref] = {"issue": number, "run_id": run_id, "status": "timeout"}
        save(self.runs_path, self.runs)

    def run(self):
        seeds = {s["ref"]: s for s in json.load(open(os.path.join(GOLD, "corpus", "seeds.json")))}
        seeds["SA02"] = json.load(open(os.path.join(GOLD, "cases", "A02", "injected_seed.json")))
        timeline = json.load(open(os.path.join(GOLD, "corpus", "timeline.json")))
        timeline += [{"op": "create", "ref": "A01"}, {"op": "create", "ref": "SA02"},
                     {"op": "create", "ref": "A02"}, {"op": "create", "ref": "A03"}]
        for ev in timeline:
            ref = ev["ref"]
            is_case = not ref.startswith("S")
            if ev["op"] == "create" and is_case:
                if self.only and ref not in self.only:
                    continue
                if ref in self.runs and self.runs[ref].get("status") == "completed":
                    continue
                c = json.load(open(os.path.join(GOLD, "cases", ref, "input.json")))
                self.workflow(True)
                opened = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                n = self.create(ref, c["title"], c["body"], c["labels_at_creation"])
                self.wait_run(ref, n, opened)
            elif ev["op"] == "create":
                s = seeds[ref]
                self.workflow(False)
                self.create(ref, s["title"], s["body"], s["labels_at_creation"])
            elif ref in self.map:
                self.workflow(False)
                n = str(self.map[ref])
                state = json.loads(gh("issue", "view", n, "-R", self.repo, "--json", "state").stdout)["state"]
                if ev["op"] == "close" and state == "OPEN":
                    reason = "not planned" if ev.get("reason") == "NOT_PLANNED" else "completed"
                    gh("issue", "close", n, "-R", self.repo, "--reason", reason)
                elif ev["op"] == "reopen" and state == "CLOSED":
                    gh("issue", "reopen", n, "-R", self.repo)
                time.sleep(1)
        self.workflow(True)
        print(f"done: {len(self.map)} issues, {len(self.runs)} case runs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--only", default="", help="comma-separated case ids (default: all)")
    a = ap.parse_args()
    Replay(a.repo, a.run_dir, set(filter(None, a.only.split(",")))).run()


if __name__ == "__main__":
    main()
