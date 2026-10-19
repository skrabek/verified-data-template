"""PreToolUse hook: stop an agent from changing protected data.

- raw/, releases/ and decisions/ cannot be written by file tools at all.
- A record file listed in any release cannot be edited.
- Changes to the rules themselves (tools/, tests/, AGENTS.md, CLAUDE.md, project.json, .claude/)
  ask the owner first, so a check cannot be weakened to make it pass.
- Shell commands that look like they modify those folders are refused, unless they run
  one of the project's own tools.

Shell detection is a heuristic, so validate.py and the release hashes remain the real check.
If this script fails it blocks the call (exit code 2) rather than letting it through.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
LOCKED = ("raw", "releases", "decisions")
RULES = ("tools", "tests", "AGENTS.md", "CLAUDE.md", "project.json", ".claude")
FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
PROJECT_TOOL = re.compile(r"^\s*(python3?|py)(\s+-\S+)*\s+\"?(\./)?tools[\\/](ingest|apply|validate|release|explain|new)\.py\b")
TOUCHES_LOCKED = re.compile(r"(^|[\s\"'/\\=])(raw|releases|decisions|records)[\\/]")
WRITES = re.compile(r"(\b(rm|rmdir|del|erase|rd|mv|move|ren|rename|cp|copy|xcopy|robocopy|truncate|chmod|chown|attrib|icacls"
                    r"|tee|touch|Remove-Item|Move-Item|Rename-Item|Copy-Item|Set-Content|Add-Content|Clear-Content"
                    r"|Out-File|New-Item|Set-ItemProperty)\b|\bsed\s+-i|\bperl\s+-i|>)", re.IGNORECASE)


def respond(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))


def released_paths() -> set[str]:
    paths = set()
    for manifest in (ROOT / "releases").glob("*/manifest.json"):
        paths |= set(json.loads(manifest.read_text(encoding="utf-8")).get("files", {}))
    return paths


def check_file(path_text: str) -> tuple[str, str] | None:
    path = Path(path_text)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        return None
    top = relative.split("/")[0]
    if top in LOCKED:
        return "deny", (f"{relative} is protected. Originals enter through tools/ingest.py, releases through "
                        "tools/release.py, and decisions only through tools/decide.py run by the owner.")
    if top == "records" and relative in released_paths():
        return "deny", (f"{relative} is part of a release and is frozen. Write a proposal in proposals/ and a "
                        "decision draft in drafts/decisions/, then ask the owner.")
    if top in RULES:
        return "ask", f"{relative} is part of the project's rules. The owner must approve this change."
    return None


def check_shell(command: str) -> tuple[str, str] | None:
    if PROJECT_TOOL.match(command) and not re.search(r"[;&|]", command):
        return None
    if TOUCHES_LOCKED.search(command) and WRITES.search(command):
        return "deny", ("This command appears to modify raw/, records/, releases/ or decisions/. Use the tools "
                        "in tools/ instead; if it is read-only, rewrite it without redirection or write commands.")
    return None


def main() -> int:
    event = json.load(sys.stdin)
    tool = event.get("tool_name", "")
    params = event.get("tool_input", {}) or {}
    verdict = None
    if tool in FILE_TOOLS:
        verdict = check_file(params.get("file_path") or params.get("notebook_path") or "")
    elif tool in SHELL_TOOLS:
        verdict = check_shell(params.get("command", ""))
    if verdict:
        respond(*verdict)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # fail closed
        print(f"guard.py failed, so the call was blocked: {error}", file=sys.stderr)
        sys.exit(2)
