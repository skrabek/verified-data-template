"""Shared helpers for the project tools. Standard library only (Python 3.10+)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PREFIX = {"source": "SRC", "claim": "CLM", "conclusion": "CON", "hypothesis": "HYP"}
TYPE_OF = {prefix: kind for kind, prefix in PREFIX.items()}
REVISION_RE = re.compile(r"^r(\d+)\.json$")
ID_RE = re.compile(r"^([A-Z]+)-(\d+)$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: cannot read JSON ({error})") from error


def dump_json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_new(path: Path, data) -> None:
    """Create a JSON file. Never overwrites an existing one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_json(data))


def replace_json(path: Path, data) -> None:
    """Atomically replace a mutable JSON file (only the register and the release pointer)."""
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_json(data))
    os.replace(temporary, path)


def make_readonly(path: Path) -> None:
    os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


def rel(root: Path, path: Path) -> str:
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def config(root: Path) -> dict:
    return load_json(root / "project.json")


def load_records(root: Path) -> dict[str, list[dict]]:
    """Map each record ID to its revisions in order: {"n", "path", "folder", "doc"}."""
    records: dict[str, list[dict]] = {}
    base = root / "records"
    if not base.exists():
        return records
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        for record_dir in sorted(p for p in folder.iterdir() if p.is_dir()):
            revisions = []
            for file in record_dir.iterdir():
                match = REVISION_RE.match(file.name)
                if match:
                    revisions.append({"n": int(match.group(1)), "path": file,
                                      "folder": folder.name, "doc": load_json(file)})
            revisions.sort(key=lambda revision: revision["n"])
            records[record_dir.name] = revisions
    return records


def current(records: dict, identity: str) -> dict | None:
    revisions = records.get(identity)
    return revisions[-1]["doc"].get("data") or {} if revisions else None


def kind_of(records: dict, identity: str) -> str | None:
    revisions = records.get(identity)
    return revisions[-1]["doc"].get("type") if revisions else None


def load_proposals(root: Path) -> dict[str, dict]:
    folder = root / "proposals"
    if not folder.exists():
        return {}
    return {path.stem: load_json(path) for path in sorted(folder.glob("PRO-*.json"))}


def load_register(root: Path) -> list[dict]:
    path = root / "decisions" / "register.json"
    return load_json(path).get("decisions", []) if path.exists() else []


def decision_status(register: list[dict]) -> dict[str, str]:
    """Effective status of each decision: accepted, rejected or superseded."""
    status = {d.get("id"): d.get("status") for d in register}
    for decision in register:
        if decision.get("status") == "accepted":
            for older in decision.get("supersedes", []):
                status[older] = "superseded"
    return status


def approving_decision(register: list[dict], proposal_id: str, include_superseded: bool = False) -> dict | None:
    status = decision_status(register)
    allowed = {"accepted", "superseded"} if include_superseded else {"accepted"}
    for decision in register:
        if (decision.get("status") == "accepted" and status.get(decision.get("id")) in allowed
                and proposal_id in decision.get("approves", [])):
            return decision
    return None


def next_id(root: Path, prefix: str) -> str:
    """Next free ID for a prefix. Assumes one writer at a time."""
    used = set(load_records(root)) | set(load_proposals(root)) | {d.get("id") for d in load_register(root)}
    numbers = [int(m.group(2)) for m in map(ID_RE.match, filter(None, used)) if m and m.group(1) == prefix]
    return f"{prefix}-{max(numbers, default=0) + 1:04d}"
