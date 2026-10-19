"""Apply an approved proposal: write each change as the next revision of its record.

Refuses unless an accepted decision approves the proposal, the proposal has not been applied,
and every target is still at the revision the proposal was written against. Checks everything
before writing anything. Never overwrites a file.

    python tools/apply.py PRO-0003
"""
from __future__ import annotations

import sys

import common as c


def apply(root, proposal_id: str) -> list[str]:
    proposal = c.load_proposals(root).get(proposal_id)
    if proposal is None:
        raise SystemExit(f"{proposal_id} does not exist.")
    decision = c.approving_decision(c.load_register(root), proposal_id)
    if decision is None:
        raise SystemExit(f"{proposal_id} is not approved. The owner approves it by running tools/decide.py.")
    records = c.load_records(root)
    if any(r["doc"].get("applied_from") == proposal_id for revisions in records.values() for r in revisions):
        raise SystemExit(f"{proposal_id} has already been applied.")
    planned = []
    for change in proposal["changes"]:
        target = change["target"]
        at = records[target][-1]["n"] if target in records else 0
        if at != change["base_revision"]:
            raise SystemExit(f"{target} is at r{at} but {proposal_id} was written against r{change['base_revision']}. "
                             "Write a new proposal against the current revision.")
        planned.append((change, at + 1))
    written = []
    for change, revision in planned:
        path = root / "records" / change["type"] / change["target"] / f"r{revision}.json"
        c.write_new(path, {
            "id": change["target"], "type": change["type"], "revision": revision,
            "created_at": c.now(), "created_by": "tools/apply.py",
            "applied_from": proposal_id, "approved_by": decision["id"], "data": change["data"],
        })
        written.append(c.rel(root, path))
    return written


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    for path in apply(c.ROOT, sys.argv[1]):
        print(f"wrote {path}")
    print("Now run: python tools/validate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
