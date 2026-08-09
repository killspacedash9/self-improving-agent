#!/usr/bin/env python3
"""Aster — self-improving repository harness.

Reads the repo's soul (SOUL.md), takes a task, asks DeepSeek for a plan as
JSON (full file contents), applies the files, syntax-checks them, runs the
test suite, repairs up to N rounds, then journals, commits, pushes — and
optionally opens a PR or comments on the originating issue.

Zero third-party dependencies (Python stdlib only). `pytest` is required for
the test gate (see requirements.txt). A `DEEPSEEK_API_KEY` env var is
required unless `--mock` is used for the offline demo.

Usage:
  python harness/runner.py --task "Add a quote() method" [--max-rounds 3]
      [--mode local|push|pr] [--branch main] [--notify-issue 12]
      [--issue 12] [--source "issue #12"] [--mock]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
JOURNAL = ROOT / "AGENT_JOURNAL.md"
SOUL = ROOT / "SOUL.md"
AGENTS = ROOT / "AGENTS.md"

ALLOWED_PREFIXES = ("src", "tests", "web", "docs", "prompts")
ALLOWED_ROOT_FILES = {"README.md", "SOUL.md"}
BLOCKED_TOPS = {
    ".github", ".git", "harness", ".venv", ".pytest_cache", "__pycache__",
    "node_modules",
}
BLOCKED_NAMES = {"AGENT_JOURNAL.md", ".env", ".gitignore"}
BLOCKED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".p8")

MAX_FILE_BYTES = 200_000
MAX_CONTEXT_BYTES = 60_000

API_BASE = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
API_URL = f"{API_BASE}/chat/completions"
MODEL = os.environ.get("AGENT_MODEL") or "deepseek-chat"

BOT_NAME = "Aster (agent-improver)"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(f"[aster] {msg}", flush=True)


def sh(args, cwd=None, check=False):
    r = subprocess.run(args, cwd=cwd or ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        log(f"command failed ({r.returncode}): {' '.join(args)}\n{r.stderr[:2000]}")
        sys.exit(1)
    return r


def git(*args) -> str:
    r = sh(["git", *args])
    return r.stdout.strip() if r.returncode == 0 else ""


def current_branch() -> str:
    return git("symbolic-ref", "--short", "HEAD") or "main"


def repo_identity() -> tuple[str | None, str | None]:
    """Return (owner, repo) from CI env or the origin remote."""
    ident = os.environ.get("GITHUB_REPOSITORY")
    if ident and "/" in ident:
        return ident.split("/", 1)
    url = git("remote", "get-url", "origin")
    m = re.search(r"(?:github\.com[/:])([^/]+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2)
    return None, None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "improvement"


def gh_api(method: str, path: str, payload: dict | None = None):
    """Minimal GitHub REST client (used for issue fetch/comment and PRs)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    if payload is not None:
        req.data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode() or "null"
            return json.loads(body)
    except urllib.error.HTTPError as e:
        log(f"github api {method} {path} -> {e.code}: {e.read().decode()[:300]}")
        return None


# ---------------------------------------------------------------------------
# context & prompting
# ---------------------------------------------------------------------------

def repo_context() -> str:
    """Render the repository (minus secrets/workflows/harness) for the model."""
    lines: list[str] = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        parts = rel.split("/")
        if any(part in BLOCKED_TOPS for part in parts):
            continue
        if p.name in BLOCKED_NAMES:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > MAX_FILE_BYTES:
            continue
        lines.append(f"--- {rel} ({size} bytes) ---\n{p.read_text(errors='replace')}")
    ctx = "\n".join(lines)
    return ctx[:MAX_CONTEXT_BYTES]


def build_messages(task: str, repairs: list[str], round_no: int) -> list[dict]:
    system = "\n\n".join(filter(None, [
        "You are Aster, the autonomous agent that lives inside this repository.",
        SOUL.read_text() if SOUL.exists() else "",
        AGENTS.read_text() if AGENTS.exists() else "",
        "Reply with a single JSON object only (no markdown fences). The object "
        'must contain: "summary" (string), "files" (object mapping relative '
        'repo paths to complete new file contents), and "soul_lessons" (array '
        "of strings, may be empty).",
    ]))
    user = [
        f"TASK (round {round_no}):\n{task}",
        "",
        "--- current repository ---",
        repo_context(),
    ]
    if repairs:
        user.append("")
        user.append("--- repair history (your previous attempt was rejected) ---")
        user.append("\n\n".join(repairs))
    user.append("")
    user.append("Produce the JSON now. Include the FULL content of every file you change.")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user)},
    ]


def call_deepseek(messages: list[dict]) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        sys.exit(
            "FATAL: DEEPSEEK_API_KEY is not set. Add it as a repository secret: "
            "Settings → Secrets and variables → Actions → DEEPSEEK_API_KEY."
        )
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 16000,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read().decode())
            content = data.get("choices", [{}])[0].get("message", {}).get("content")
            if not content:
                raise ValueError(f"empty completion: {str(data)[:300]}")
            return content
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                log(f"api {e.code} — retrying in {5 * (attempt + 1)}s")
                time.sleep(5 * (attempt + 1))
                continue
            sys.exit(f"FATAL: DeepSeek API error {e.code}: {body}")
        except Exception as e:  # noqa: BLE001 — network/parse fallback
            if attempt == 2:
                sys.exit(f"FATAL: DeepSeek API unreachable: {e}")
            log(f"api error: {e} — retrying in {5 * (attempt + 1)}s")
            time.sleep(5 * (attempt + 1))
    sys.exit("FATAL: DeepSeek API retries exhausted")


# ---------------------------------------------------------------------------
# response handling
# ---------------------------------------------------------------------------

def validate_path(path: str) -> str | None:
    """Return the normalized relative path if writable, else None."""
    p = path.strip().replace("\\", "/").lstrip("/")
    if not p:
        return None
    parts = p.split("/")
    if any(part in ("..", "", ".") for part in parts):
        return None
    if p.endswith(BLOCKED_SUFFIXES) or parts[0] in BLOCKED_TOPS or p in BLOCKED_NAMES:
        return None
    if parts[0] in ALLOWED_PREFIXES or p in ALLOWED_ROOT_FILES:
        return p
    return None

def parse_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"response is not valid JSON ({e}); first 200 chars: {raw[:200]}") from e
    if not isinstance(data, dict):
        raise ValueError("response JSON must be an object")
    summary = str(data.get("summary", "")).strip()
    files = data.get("files", {}) or {}
    lessons = data.get("soul_lessons", []) or []
    if not isinstance(files, dict):
        raise ValueError("'files' must be an object")
    if not isinstance(lessons, list):
        lessons = []
    clean: dict[str, str] = {}
    for path, content in files.items():
        vp = validate_path(str(path))
        if not vp:
            raise ValueError(
                f"path '{path}' is not writable "
                "(allowed: src/, tests/, web/, docs/, prompts/, README.md, SOUL.md)"
            )
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"content for '{path}' is missing or empty")
        if len(content.encode()) > MAX_FILE_BYTES:
            raise ValueError(f"content for '{path}' is too large")
        clean[vp] = content
    return {"summary": summary, "files": clean, "lessons": [str(x) for x in lessons][:5]}


def apply_files(files: dict[str, str]) -> list[str]:
    changed: list[str] = []
    for path, content in files.items():
        target = (ROOT / path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.rstrip() + "\n")
        changed.append(path)
    return changed


def syntax_check(changed: list[str]) -> list[str]:
    bad = []
    for path in changed:
        if not path.endswith(".py"):
            continue
        src = (ROOT / path).read_text()
        try:
            compile(src, path, "exec")
        except SyntaxError as e:
            bad.append(f"{path}:{e.lineno}: {e.msg}")
    return bad


def run_tests() -> tuple[bool, str]:
    try:
        import pytest  # noqa: F401

        cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short", "tests/"]
    except ImportError:
        log("pytest not installed — falling back to unittest discover")
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    return r.returncode == 0, out[-8000:]


# ---------------------------------------------------------------------------
# journal, soul lessons, git, notifications
# ---------------------------------------------------------------------------

def journal_entry(source: str, task: str, summary: str, changed: list[str],
                  ok: bool, sha: str = "", note: str = "") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    head = f"## {ts} — {source}"
    status = "✅ passed" if ok else "❌ failed"
    files = f" · {len(changed)} file(s): {', '.join(changed)}" if changed else ""
    line = f"**Result:** {status}{files}" + (f" · commit `{sha}`" if sha else "")
    tail = f"{summary}{(' — ' + note) if note else ''}"
    entry = "\n\n".join([head, f"**Task:** {' '.join(task.split())[:220]}", line, tail])
    text = JOURNAL.read_text() if JOURNAL.exists() else "# Agent Journal\n"
    lines = text.rstrip().splitlines()
    insert_at = 1 if lines and lines[0].startswith("# ") else 0
    new = "\n".join(lines[:insert_at] + [entry, ""] + lines[insert_at:])
    JOURNAL.write_text(new.rstrip() + "\n")


def apply_lessons(lessons: list[str]) -> None:
    if not lessons or not SOUL.exists():
        return
    text = SOUL.read_text()
    block = "\n## Lessons\n\n" + "\n".join(f"- {lesson}" for lesson in lessons) + "\n"
    marker = "\n## Lessons\n"
    if marker in text:
        text = text.split(marker)[0] + block
    else:
        text = text.rstrip() + "\n" + block
    SOUL.write_text(text)


def commit_push(branch: str, summary: str, mode: str, task: str) -> tuple[str | None, str]:
    """Stage everything, commit as the bot, then push or open a PR."""
    if git("status", "--porcelain") == "":
        return None, "no changes to commit"
    git("config", "user.name", BOT_NAME)
    git("config", "user.email", BOT_EMAIL)
    git("add", "-A")
    r = sh(["git", "commit", "-m", f"[agent] {summary[:120]}", "-m", f"Task: {' '.join(task.split())[:200]}"])
    if r.returncode != 0:
        return None, f"commit failed: {r.stderr[:400]}"
    sha = git("rev-parse", "--short", "HEAD")
    owner, repo = repo_identity()
    remote = git("remote")
    if mode == "local":
        return sha, f"committed {sha} locally (mode=local, not pushed)"
    if not remote:
        return sha, f"committed {sha} (no remote configured, not pushed)"
    if mode == "pr":
        if not owner:
            return sha, f"committed {sha} (no GitHub remote — PR skipped)"
        head = f"agent/{slug(summary)}"
        git("checkout", "-b", head)
        git("push", "-u", "origin", head)
        url = open_pr(branch, head, summary, task)
        return sha, f"PR opened: {url or 'failed to open PR'} ({head})"
    r = sh(["git", "push", "origin", f"HEAD:{branch}"])
    if r.returncode != 0:
        return sha, f"committed {sha} but push failed: {r.stderr[:300]}"
    return sha, f"pushed {sha} → {branch}"


def open_pr(base: str, head: str, summary: str, task: str) -> str | None:
    owner, repo = repo_identity()
    if not owner:
        return None
    res = gh_api("POST", f"/repos/{owner}/{repo}/pulls", {
        "title": f"[agent] {summary[:100]}",
        "head": head,
        "base": base,
        "body": f"Automated change by Aster.\n\n**Task:** {' '.join(task.split())[:300]}",
    })
    return (res or {}).get("html_url")


def notify_issue(number: int, title: str, summary: str, changed: list[str],
                 sha: str, ok: bool, note: str = "") -> None:
    owner, repo = repo_identity()
    if not owner:
        return
    lines = [f"🤖 **Aster** — {title}", ""]
    status = "✅ completed" if ok else "❌ failed"
    lines.append(f"**Result:** {status} · {len(changed)} file(s) changed"
                 + (f" · commit `{sha}`" if sha else ""))
    if summary:
        lines.append(f"**Summary:** {summary}")
    if changed:
        lines.append(f"**Files:** {', '.join(changed)}")
    if note:
        lines.append(f"**Note:** {note}")
    run_id = os.environ.get("GITHUB_RUN_ID")
    server = os.environ.get("GITHUB_SERVER_URL")
    repo_env = os.environ.get("GITHUB_REPOSITORY")
    if run_id and server and repo_env:
        lines.append(f"**Run:** {server}/{repo_env}/actions/runs/{run_id}")
    gh_api("POST", f"/repos/{owner}/{repo}/issues/{number}/comments", {"body": "\n".join(lines)})


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Aster self-improvement harness")
    ap.add_argument("--task", help="the task to improve the repo with (required unless --issue/--mock)")
    ap.add_argument("--issue", type=int, default=0, help="pull the task from a GitHub issue (uses GITHUB_TOKEN)")
    ap.add_argument("--source", default="manual run", help="where the task came from (for the journal)")
    ap.add_argument("--mode", choices=["local", "push", "pr"], default="local", help="how to publish the change")
    ap.add_argument("--branch", default=None, help="branch to push to (default: current branch)")
    ap.add_argument("--max-rounds", type=int, default=3, help="repair attempts per run")
    ap.add_argument("--notify-issue", type=int, default=0, help="comment the result on this issue number")
    ap.add_argument("--mock", action="store_true", help="offline demo: use the canned response, no API call")
    args = ap.parse_args()

    if args.issue:
        owner, repo = repo_identity()
        data = gh_api("GET", f"/repos/{owner or ''}/{repo or ''}/issues/{args.issue}") if owner else None
        if data and data.get("title"):
            args.task = f"Issue #{args.issue}: {data['title']}\n\n{data.get('body') or ''}"
            args.source = f"issue #{args.issue}"
            if not args.notify_issue:
                args.notify_issue = args.issue
            log(f"fetched task from issue #{args.issue}")
        else:
            args.task = f"Issue #{args.issue} (could not fetch body — is GITHUB_TOKEN set?)"
            log("warning: could not fetch issue body")
    if not args.task and not args.mock:
        ap.error("--task is required (or use --issue N, or --mock)")

    branch = args.branch or current_branch()
    task = args.task or "Offline demo: add a random-proverb quote() method to TinyMind."
    log(f"soul: SOUL.md · model: {MODEL} · mode: {args.mode} · branch: {branch}")
    log(f"task: {' '.join(task.split())[:140]}")

    repairs: list[str] = []
    changed: list[str] = []
    summary = ""
    lessons: list[str] = []
    ok = False

    for round_no in range(1, max(1, min(args.max_rounds, 5)) + 1):
        log(f"round {round_no}: asking {MODEL}…")
        if args.mock:
            ns: dict = {}
            exec((HARNESS / "mock_response.py").read_text(), ns)  # noqa: S102 — offline fixture
            raw = json.dumps(ns["RESPONSE"])
            log("mock mode: using canned response (no API call)")
        else:
            raw = call_deepseek(build_messages(task, repairs, round_no))
        try:
            resp = parse_response(raw)
        except ValueError as e:
            repairs.append(f"Round {round_no}: your response was rejected — {e}. Return valid JSON.")
            log(f"round {round_no}: bad response — {e}")
            continue
        summary, files, lessons = resp["summary"], resp["files"], resp["lessons"]
        if not files:
            log(f"round {round_no}: agent declined — {summary or 'no changes proposed'}")
            summary = summary or "No changes proposed."
            break
        changed = apply_files(files)
        log(f"round {round_no}: applied {len(changed)} file(s): {', '.join(changed)}")
        bad = syntax_check(changed)
        if bad:
            repairs.append("Round %d: syntax errors in your files:\n%s\nFix and return the full corrected files."
                           % (round_no, "\n".join(bad)))
            log(f"round {round_no}: syntax errors — sending back for repair")
            continue
        ok, output = run_tests()
        if ok:
            log(f"round {round_no}: tests passed ✅")
            break
        repairs.append(
            "Round %d: tests FAILED with your change. Output:\n%s\n"
            "Fix your change and return the full corrected files. Do not weaken or delete tests."
            % (round_no, output)
        )
        log(f"round {round_no}: tests failed — sending back for repair")

    if ok:
        apply_lessons(lessons)
        journal_entry(args.source, task, summary or "completed", changed, True)
        sha, note = commit_push(branch, summary or "improvement", args.mode, task)
        log(note)
        if args.notify_issue:
            notify_issue(args.notify_issue, summary[:120], summary, changed, sha or "", True)
        print(f"\n[aster] DONE — {note}")
        sys.exit(0)

    # failure path: restore the tree, record the failure honestly, keep journal-only commit
    log(f"FAILED: could not satisfy the task within {args.max_rounds} rounds")
    if git("rev-parse", "--verify", "HEAD"):
        sh(["git", "restore", "."])
        for f in git("ls-files", "--others", "--exclude-standard").splitlines():
            (ROOT / f).unlink(missing_ok=True)
    journal_entry(args.source, task, summary or "no viable change found", [], False,
                  note=f"failed after {args.max_rounds} rounds")
    sha, note = commit_push(branch, f"journal: failed run ({args.source})", args.mode, task)
    if args.notify_issue:
        notify_issue(args.notify_issue, summary or "failed", summary or "Could not complete the task",
                     [], sha or "", False, note=f"failed after {args.max_rounds} rounds")
    log(note)
    sys.exit(1)


if __name__ == "__main__":
    main()
