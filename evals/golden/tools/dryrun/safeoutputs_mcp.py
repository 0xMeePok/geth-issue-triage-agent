#!/usr/bin/env python3
"""Local stand-in for gh-aw's `safeoutputs` MCP server, used only for the dry run.

    python3 safeoutputs_mcp.py --case-file so-case.json
    (so-case.json: {"lock": ..., "issue": N, "labels": ..., "out": ..., "log": ...})

Speaks MCP (JSON-RPC 2.0 over stdio). Serves the exact tool definitions gh-aw v0.92.0
returned in a live run (safeoutputs_tools.json) and enforces the limits compiled into the
lock file (GH_AW_SAFE_OUTPUTS_CONFIG): allowed and blocked labels, labels per call, number
of calls per tool, links per comment, and the triggering issue as the only target.
Accepted calls are appended to --out (the agent_output items); every call, accepted or
rejected, is appended to --log. Nothing is written to GitHub.
"""
import argparse
import fnmatch
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(lock_path):
    for line in open(lock_path):
        m = re.match(r'\s*GH_AW_SAFE_OUTPUTS_CONFIG: "(.*)"\s*$', line)
        if m:
            return json.loads(m.group(1).encode().decode("unicode_escape"))
    sys.exit("GH_AW_SAFE_OUTPUTS_CONFIG not found in lock file")


class Server:
    def __init__(self, a):
        self.cfg = load_config(a["lock"])
        self.issue = int(a["issue"])
        self.repo_labels = set(json.load(open(a["labels"])))
        self.out, self.log = a["out"], a["log"]
        self.calls = {}
        tools = json.load(open(os.path.join(HERE, "safeoutputs_tools.json")))["tools"]
        self.tools = []
        for t in tools:
            t = json.loads(json.dumps(t).replace("Target: 2.", f"Target: {self.issue}."))
            self.tools.append(t)

    def record(self, path, obj):
        with open(path, "a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def check_target(self, args):
        n = args.get("item_number")
        if n not in (None, "", self.issue, str(self.issue)):
            return f"target must be the triggering issue #{self.issue}; got {n}"
        return None

    def call(self, name, args):
        cfg = self.cfg.get(name, {})
        limit = cfg.get("max")
        if limit is not None and self.calls.get(name, 0) >= int(limit):
            return False, f"{name}: maximum {limit} call(s) reached"
        err = self.check_target(args)
        if err and name in ("add_labels", "add_comment"):
            return False, err
        if name == "add_labels":
            labels = [l if isinstance(l, str) else (l or {}).get("name", "") for l in args.get("labels") or []]
            if not labels:
                return False, "add_labels: no labels given"
            if len(labels) > int(cfg.get("max_labels", 10)):
                return False, f"add_labels: at most {cfg.get('max_labels')} labels per call"
            for l in labels:
                if any(fnmatch.fnmatch(l, p) for p in cfg.get("blocked", [])):
                    return False, f"add_labels: label '{l}' is blocked"
                if cfg.get("allowed") and not any(fnmatch.fnmatch(l, p) for p in cfg["allowed"]):
                    return False, f"add_labels: label '{l}' is not in the allowed list"
                if l not in self.repo_labels:
                    return False, f"add_labels: label '{l}' does not exist in the repository"
            item = {"type": "add_labels", "labels": labels}
            msg = f"Labels will be added to #{self.issue}: {', '.join(labels)}"
        elif name == "add_comment":
            body = args.get("body") or ""
            if not body.strip():
                return False, "add_comment: body is required"
            links = len(re.findall(r"https?://", body))
            if links > int(cfg.get("max_links", 50)):
                return False, f"add_comment: {links} links exceed max-links {cfg.get('max_links')}"
            item = {"type": "add_comment", "body": body}
            msg = f"Comment will be posted on #{self.issue}"
        elif name == "noop":
            item = {"type": "noop", "message": args.get("message") or args.get("reason") or ""}
            msg = "No-op recorded"
        elif name in ("missing_tool", "missing_data", "report_incomplete"):
            item = {"type": name, **args}
            msg = f"{name} recorded"
        else:
            return False, f"unknown tool {name}"
        self.calls[name] = self.calls.get(name, 0) + 1  # only accepted calls use up the budget
        self.record(self.out, item)
        return True, msg

    def handle(self, req):
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            ver = (req.get("params") or {}).get("protocolVersion", "2025-06-18")
            return {"protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "safeoutputs", "version": "dryrun-1"}}
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "ping":
            return {}
        if method == "tools/call":
            p = req.get("params") or {}
            ok, msg = self.call(p.get("name"), p.get("arguments") or {})
            self.record(self.log, {"tool": p.get("name"), "arguments": p.get("arguments"), "accepted": ok, "result": msg})
            return {"content": [{"type": "text", "text": json.dumps({"result": "success" if ok else "error", "message": msg})}],
                    "isError": not ok}
        if rid is None:
            return None  # notification
        raise KeyError(method)

    def serve(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            try:
                res = self.handle(req)
                if req.get("id") is not None:
                    resp = {"jsonrpc": "2.0", "id": req["id"], "result": res}
                else:
                    continue
            except KeyError as e:
                resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32601, "message": f"method not found: {e}"}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-file", required=True)
    Server(json.load(open(ap.parse_args().case_file))).serve()


if __name__ == "__main__":
    main()
