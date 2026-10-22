#!/usr/bin/env python3
"""Same golden dry run as dryrun_cursor.py, calling Copilot gpt-4.1.

The inputs, prompt, skill, scripts and safe-output limits are the ones the Cursor
run used. The model call is Copilot chat completions (the API that finished run
39629381767), not the Cursor CLI. The token is taken from `gh auth token` and is
not written to the transcript.

    python3 evals/golden/tools/dryrun_copilot.py \
        --run-dir evals/golden/runs/NAME --ws-root /some/scratch/dir \
        [--only H01] [--model gpt-4.1] [--resume]
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

import dryrun_cursor as dc

sys.path.insert(0, os.path.join(dc.DRY))
from safeoutputs_mcp import Server  # noqa: E402

SCRIPTS = [
    "python3 .claude/skills/geth-issue-triage/scripts/check_template.py",
    "python3 .claude/skills/geth-issue-triage/scripts/find_duplicates.py",
    "python3 .claude/skills/geth-issue-triage/scripts/validate_labels.py",
    "python3 .claude/skills/geth-issue-triage/scripts/render_comment.py",
]
READ_BINS = {"cat", "head", "ls", "grep", "wc"}
MAX_TURNS = 30
API = "https://api.githubcopilot.com/chat/completions"


def token():
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def redact(text):
    import re
    return re.sub(r"(gho_|ghu_|github_pat_|ghp_|ghs_)[A-Za-z0-9_]+", "[redacted]", text or "")


def chat_once(tok, body):
    """POST chat completions. The bearer token stays in a 0600 curl config, not argv."""
    tmp = tempfile.mkdtemp(prefix="copilot-chat-")
    os.chmod(tmp, 0o700)
    body_path = os.path.join(tmp, "body.json")
    cfg_path = os.path.join(tmp, "curl.cfg")
    headers = [
        "Authorization: Bearer " + tok,
        "Content-Type: application/json",
        "Accept: application/json",
        "Editor-Version: vscode/1.95.0",
        "Editor-Plugin-Version: copilot-chat/0.22.0",
        "Copilot-Integration-Id: vscode-chat",
        "User-Agent: GithubCopilot/1.0",
    ]
    try:
        with open(body_path, "w") as f:
            json.dump(body, f)
        fd = os.open(cfg_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            for h in headers:
                f.write('header = "%s"\n' % h.replace('"', ""))
            f.write('url = "%s"\n' % API)
        r = subprocess.run(
            ["curl", "-sS", "-w", "\n%{http_code}", "-K", cfg_path, "--data-binary", "@" + body_path],
            capture_output=True, text=True, timeout=120)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    raw = r.stdout or ""
    if "\n" not in raw:
        raise RuntimeError(redact((raw or r.stderr or "empty curl response"))[:500])
    payload, status = raw.rsplit("\n", 1)
    status = status.strip()
    try:
        data = json.loads(payload) if payload.strip() else {}
    except json.JSONDecodeError:
        raise RuntimeError(f"HTTP {status}: non-json body: {redact(payload[:300])}")
    if status != "200":
        err = data.get("error") or data or payload[:300]
        raise RuntimeError(f"HTTP {status}: {redact(json.dumps(err)[:500])}")
    if not data.get("choices"):
        raise RuntimeError(f"HTTP {status}: response had no choices")
    return data


def chat(tok, body):
    """Retry a transport failure a couple of times. A finished model decision is not retried."""
    last = None
    for attempt in range(3):
        try:
            return chat_once(tok, body)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            last = e
            msg = str(e)
            retry = attempt < 2 and (
                "HTTP 429" in msg or "HTTP 5" in msg or "HTTP 000" in msg
                or "non-json" in msg or "no choices" in msg or "empty curl" in msg
                or "timed out" in msg)
            if not retry:
                raise
            time.sleep(30 * (attempt + 1))
    raise last


PY_REJECT = (
    "rejected: python3 may run only these four commands, copied from SKILL.md, "
    "with positional arguments and no --flags: "
    + "; ".join(SCRIPTS)
    + ". Read the procedure with: cat .claude/skills/geth-issue-triage/SKILL.md. "
    "Do not invent script names and do not retry a rejected command."
)


def allow_bash(cmd, ws):
    if any(c in cmd for c in ";|&<>`$()\n"):
        return "rejected: shell operators are not allowed"
    try:
        parts = shlex.split(cmd)
    except ValueError as e:
        return f"rejected: {e}"
    if not parts:
        return "rejected: empty command"
    if parts[0] == "python3":
        joined = " ".join(parts[:2])
        if not any(joined == prefix for prefix in SCRIPTS):
            return PY_REJECT
        if len(parts) < 3:
            return PY_REJECT
        return None
    if parts[0] not in READ_BINS:
        return f"rejected: {parts[0]} is not on the allowlist"
    root = os.path.realpath(ws)
    for arg in parts[1:]:
        if arg.startswith("-"):
            continue
        if ".." in arg.split("/"):
            return f"rejected: path escapes the workspace: {arg}"
        path = os.path.realpath(arg if os.path.isabs(arg) else os.path.join(ws, arg))
        if path != root and not path.startswith(root + os.sep):
            return f"rejected: path escapes the workspace: {arg}"
    return None


def run_bash(cmd, ws):
    err = allow_bash(cmd, ws)
    if err:
        return err
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "LANG": "en_US.UTF-8", "HOME": ws,
           "TMPDIR": os.path.join(ws, ".gh-aw", "agent-tmp")}
    try:
        r = subprocess.run(cmd, shell=True, cwd=ws, env=env, capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        return "rejected: command timed out"
    out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    err_l = (r.stderr or "").lower()
    if r.returncode != 0 and parts_are_skill(cmd) and (
            "usage:" in err_l or "unrecognized arguments" in err_l or "error:" in err_l):
        out += ("\nThis command does not match SKILL.md. "
                "cat .claude/skills/geth-issue-triage/SKILL.md and copy the command from there. "
                "Do not retry this exact command.")
    if len(out) > 16000:
        out = out[:16000] + "\n...[truncated]"
    return f"exit {r.returncode}\n{out}"


def parts_are_skill(cmd):
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return False
    return len(parts) >= 2 and " ".join(parts[:2]) in SCRIPTS


def tool_defs():
    tools = json.load(open(os.path.join(dc.DRY, "safeoutputs_tools.json")))["tools"]
    specs = [{
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run one allowlisted command. The first command must be "
                           "cat .claude/skills/geth-issue-triage/SKILL.md and later python3 commands must be "
                           "copied from that file. python3 may run only the four scripts named there. "
                           "cat, head, ls, grep and wc may read the workspace. "
                           "No pipes, redirects or other commands.",
            "parameters": {"type": "object", "additionalProperties": False,
                           "properties": {"command": {"type": "string"}}, "required": ["command"]},
        },
    }]
    for t in tools:
        specs.append({"type": "function", "function": {
            "name": t["name"], "description": t["description"][:1500],
            "parameters": t["inputSchema"]}})
    return specs


def run_copilot(model, ws, prompt, transcript, timeout):
    if model.startswith("grok"):
        model = "gpt-4.1"
    case = json.load(open(os.path.join(os.path.dirname(ws), "so-case.json")))
    server = Server(case)
    tok = token()
    messages = [{"role": "user", "content": prompt}]
    tools = tool_defs()
    t0 = time.time()
    usage = {"input_tokens": 0, "output_tokens": 0}
    concrete = model
    code = 1
    with open(transcript, "w") as log:
        for turn in range(1, MAX_TURNS + 1):
            if time.time() - t0 > timeout:
                code = "timeout"
                break
            try:
                data = chat(tok, {"model": model, "messages": messages, "tools": tools, "temperature": 0})
            except Exception as e:
                log.write(json.dumps({"type": "error", "turn": turn, "message": redact(str(e))}) + "\n")
                code = 1
                break
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            concrete = data.get("model") or concrete
            u = data.get("usage") or {}
            usage["input_tokens"] += u.get("prompt_tokens") or 0
            usage["output_tokens"] += u.get("completion_tokens") or 0
            calls = msg.get("tool_calls") or []
            log.write(json.dumps({"type": "turn", "turn": turn, "model": concrete,
                                  "finish": choice.get("finish_reason"), "tools": [c.get("function", {}).get("name") for c in calls],
                                  "text": (msg.get("content") or "")[:400]}, ensure_ascii=False) + "\n")
            assistant = {"role": "assistant", "content": msg.get("content") or None}
            if calls:
                assistant["tool_calls"] = calls
            messages.append(assistant)
            if not calls:
                done = any(server.calls.get(n) for n in ("add_labels", "add_comment", "noop"))
                code = 0 if done else 1
                break
            for call in calls:
                fn = call.get("function") or {}
                name = fn.get("name")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                log.write(json.dumps({"type": "tool_call", "subtype": "started",
                                      "tool_call": {"name": name, "arguments": args}}, ensure_ascii=False) + "\n")
                if name == "bash":
                    result = run_bash(str(args.get("command") or ""), ws)
                else:
                    ok, result = server.call(name, args)
                    server.record(server.log, {"tool": name, "arguments": args, "accepted": ok, "result": result})
                    result = json.dumps({"result": "success" if ok else "error", "message": result})
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": result[:16000]})
        else:
            code = 1
        log.write(json.dumps({"type": "result", "result": "", "model": concrete, "usage": usage}) + "\n")
    return code, round(time.time() - t0, 1)


if __name__ == "__main__":
    if "--model" not in sys.argv:
        sys.argv[1:1] = ["--model", "gpt-4.1"]
    dc.run_agent = run_copilot
    dc.main()
