"""Freeze the current state as a numbered release.

Refuses if validation fails. Writes releases/NNN/manifest.json (the SHA-256 of every preserved
file, record, proposal and the decision register) and releases/NNN/view.json (the accepted
conclusions with their evidence chains), makes both read-only, and points releases/current.json
at the new release. From then on, validate.py fails if any listed file changes.

    python tools/release.py "First import of the 2025 contracts"
"""
from __future__ import annotations

import sys
from pathlib import Path

import common as c
from validate import validate


def build_view(root: Path) -> list[dict]:
    records = c.load_records(root)
    decisions = {d["id"]: d for d in c.load_register(root)}

    def chain(claim_id):
        claim = c.current(records, claim_id) or {}
        source = c.current(records, claim.get("source", "")) or {}
        return {"claim": claim_id, "quote": claim.get("quote"), "locator": claim.get("locator"),
                "source": claim.get("source"), "source_title": source.get("title"), "object": source.get("object")}

    view = []
    for identity, revisions in records.items():
        doc = revisions[-1]["doc"]
        data = doc.get("data") or {}
        if doc.get("type") != "conclusion" or data.get("status") != "accepted":
            continue
        view.append({
            "id": identity, "revision": doc["revision"], "proposition": data["proposition"],
            "supporting": [chain(claim) for claim in data.get("supporting_claims", [])],
            "contradicting": [chain(claim) for claim in data.get("contradicting_claims", [])],
            "decisions": [{"id": d, "quote": decisions[d]["quote"]} for d in data.get("decisions", []) if d in decisions],
            "applied_from": doc.get("applied_from"), "approved_by": doc.get("approved_by"),
            "notes": data.get("notes", ""),
        })
    return view


def release(root: Path, note: str) -> str:
    errors, _ = validate(root)
    if errors:
        raise SystemExit("Validation failed; fix these first:\n" + "\n".join(errors))
    releases = root / "releases"
    numbers = [int(p.name) for p in releases.iterdir() if p.is_dir() and p.name.isdigit()] if releases.exists() else []
    number = f"{max(numbers, default=0) + 1:03d}"
    files = {}
    for folder in ("raw", "records", "proposals"):
        for path in sorted(p for p in (root / folder).rglob("*") if p.is_file()):
            files[c.rel(root, path)] = c.sha256_file(path)
    register = root / "decisions" / "register.json"
    files[c.rel(root, register)] = c.sha256_file(register)
    out = releases / number
    c.write_new(out / "manifest.json", {"release": number, "created_at": c.now(), "note": note, "files": files})
    c.write_new(out / "view.json", {"release": number, "accepted_conclusions": build_view(root)})
    for path in out.iterdir():
        c.make_readonly(path)
    c.replace_json(releases / "current.json", {"release": number, "manifest": f"releases/{number}/manifest.json",
                                               "view": f"releases/{number}/view.json"})
    return number


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    print(f"Release {release(c.ROOT, sys.argv[1])} written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
