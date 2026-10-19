"""Record an owner decision. Only a person at an interactive terminal can run this.

The agent prepares a draft in drafts/decisions/ saying what is being decided. You read it,
answer accept or reject, and type the decision in your own words. Your words are stored
verbatim. The register before the change is saved under decisions/history/ first, so no
earlier decision can be lost or quietly rewritten.

    python tools/decide.py drafts/decisions/approve-PRO-0003.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import common as c


def record(root: Path, draft_path: Path, quote: str, status: str) -> dict:
    """Append one decision to the register. Kept separate from the prompts so it can be tested."""
    if status not in {"accepted", "rejected"}:
        raise ValueError("status must be accepted or rejected")
    if not quote.strip():
        raise ValueError("the decision needs your own words")
    draft = c.load_json(draft_path)
    register_path = root / "decisions" / "register.json"
    before = register_path.read_bytes()
    register = json.loads(before)
    identity = c.next_id(root, "DEC")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    history = root / "decisions" / "history" / f"{stamp}-before-{identity}" / "register.json"
    history.parent.mkdir(parents=True)
    history.write_bytes(before)
    c.make_readonly(history)
    decision = {
        "id": identity,
        "recorded_at": c.now(),
        "status": status,
        "statement": draft["statement"],
        "quote": quote.strip(),
        "responds_to": draft["responds_to"],
        "approves": draft.get("approves", []),
        "propositions": draft.get("propositions", []),
        "supersedes": draft.get("supersedes", []),
        "limits": draft.get("limits", ""),
        "draft": c.rel(root, draft_path),
    }
    register["decisions"].append(decision)
    c.replace_json(register_path, register)
    return decision


def interactive() -> bool:
    """True only for a real console. On Windows the null device also reports isatty(), so ask the console."""
    if not sys.stdin.isatty():
        return False
    if os.name == "nt":
        import ctypes
        import msvcrt
        mode = ctypes.c_uint()
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    if not interactive():
        print("decide.py records your own decision. Run it yourself in an interactive terminal "
              "(PowerShell or Windows Terminal; in Git Bash prefix it with winpty).")
        return 1
    draft_path = Path(sys.argv[1]).resolve()
    draft = c.load_json(draft_path)
    print(json.dumps(draft, indent=2, ensure_ascii=False))
    try:
        choice = input("\nAccept or reject this? [a/r]: ").strip().lower()
        if choice not in {"a", "r"}:
            print("Nothing recorded.")
            return 1
        quote = input("Your decision, in your own words (stored verbatim): ")
        if input("Record it? [y/N]: ").strip().lower() != "y":
            print("Nothing recorded.")
            return 1
    except EOFError:
        print("\nNothing recorded.")
        return 1
    decision = record(c.ROOT, draft_path, quote, "accepted" if choice == "a" else "rejected")
    print(f"Recorded {decision['id']} ({decision['status']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
