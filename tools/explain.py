"""Show why a value is what it is: the conclusion, its claims, their sources and any decisions.

    python tools/explain.py CON-0004
    python tools/explain.py --subject "Invoice 4471"
"""
from __future__ import annotations

import sys

import common as c


def explain(root, identity: str) -> str:
    records = c.load_records(root)
    decisions = {d["id"]: d for d in c.load_register(root)}
    data = c.current(records, identity)
    if data is None:
        return f"{identity} does not exist."
    lines = [f"{identity} r{records[identity][-1]['n']}: {data.get('proposition') or data.get('statement')}"
             f"  [{data.get('status', c.kind_of(records, identity))}]"]
    for label in ("supporting_claims", "contradicting_claims"):
        for claim_id in data.get(label, []):
            claim = c.current(records, claim_id) or {}
            source = c.current(records, claim.get("source", "")) or {}
            lines.append(f"  {label.split('_')[0]} {claim_id}: \"{claim.get('quote')}\" at {claim.get('locator')}")
            lines.append(f"      from {claim.get('source')} {source.get('title')} ({source.get('use')}) {source.get('object')}")
    for decision_id in data.get("decisions", []):
        decision = decisions.get(decision_id, {})
        lines.append(f"  decision {decision_id}: \"{decision.get('quote')}\" ({decision.get('recorded_at')})")
    doc = records[identity][-1]["doc"]
    if doc.get("applied_from"):
        lines.append(f"  applied from {doc['applied_from']}, approved by {doc.get('approved_by')}")
    if data.get("notes"):
        lines.append(f"  notes: {data['notes']}")
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--subject":
        records = c.load_records(c.ROOT)
        matches = [i for i in records if (c.current(records, i).get("proposition") or {}).get("subject") == sys.argv[2]]
        print("\n\n".join(explain(c.ROOT, i) for i in matches) or "No records for that subject.")
        return 0
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    print(explain(c.ROOT, sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
