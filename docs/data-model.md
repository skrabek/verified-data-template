# Data model

Every accepted value rests on a chain anyone can follow back to an original file:

```text
raw file (hashed, read-only)
  └─ source      SRC  what the file is, where it came from, whether it may count as evidence
      └─ claim   CLM  what the source says, at an exact locator, in its exact words
          └─ conclusion CON  the value the project accepts, with supporting and contradicting claims
                 ▲
                 └─ approved by a decision (DEC) recorded by the owner, directly or via a proposal (PRO)
hypothesis HYP: an idea from anyone, with no evidential weight
```

The examples use an invoice, but nothing in the tools depends on the subject matter.

## Record files

Each record is a folder of revisions: `records/<type>/<ID>/r1.json`, `r2.json`, ... A revision is never
overwritten. Every file has the same envelope:

```json
{
  "id": "CLM-0001",
  "type": "claim",
  "revision": 1,
  "created_at": "2026-10-19T15:00:00+00:00",
  "created_by": "agent",
  "applied_from": null,
  "data": { }
}
```

Revisions after r1 have `applied_from` (the proposal) and `approved_by` (the decision), written by `tools/apply.py`.

## Propositions

Claims, conclusions and decisions describe the same thing the same way, so they can be compared exactly:

```json
{ "subject": "Invoice 4471", "predicate": "total_amount", "value": "1,250.00 CAD" }
```

Pick stable subject names and a fixed list of predicates (list them under `predicates` in `project.json`
to have them enforced). Store values as the source writes them; put normalized forms in a separate
inferred claim.

## source (SRC)

Created only by `tools/ingest.py`.

| Field | Meaning |
|---|---|
| `title`, `class` | What the file is. `class` is your own vocabulary (contract, invoice, email, ai_generated...). |
| `use` | `eligible` (can support accepted conclusions), `context` (leads only) or `excluded`. |
| `use_reason` | Required when `use` is not `eligible`. |
| `provenance` | Where the file came from, from whom, when. |
| `original_filename`, `object`, `sha256` | The preserved copy and its hash. |

Classes listed in `project.json` under `zero_weight_classes` can never be `eligible`.

## claim (CLM)

```json
{
  "source": "SRC-0001",
  "locator": "page 2, line 14",
  "quote": "Total due: $1,250.00 CAD",
  "proposition": { "subject": "Invoice 4471", "predicate": "total_amount", "value": "1,250.00 CAD" },
  "kind": "stated",
  "reasoning": ""
}
```

`kind` is `stated` when the source says it, `inferred` when it is worked out (then `reasoning` is required).

## conclusion (CON)

```json
{
  "proposition": { "subject": "Invoice 4471", "predicate": "total_amount", "value": "1,250.00 CAD" },
  "status": "proposed",
  "supporting_claims": ["CLM-0001"],
  "contradicting_claims": ["CLM-0007"],
  "decisions": [],
  "notes": "CLM-0007 is the unsigned draft; the signed copy governs."
}
```

`status` is `proposed`, `accepted`, `rejected` or `superseded`. An accepted conclusion needs:

- human approval: either a decision in `decisions` whose `propositions` contain this exact proposition, or
  a revision applied from an approved proposal; and
- a basis: supporting claims from eligible sources, or that decision; and
- `notes` explaining the choice when contradicting claims exist.

Supporting claims must state exactly the same proposition. Contradicting claims must be about the same
subject and predicate.

## hypothesis (HYP)

```json
{ "statement": "Invoice 4471 may be a duplicate of 4468", "reasoning": "Same amount and date", "related": ["CLM-0001"] }
```

## Proposal (PRO), `proposals/PRO-0001.json`

A complete description of a change, written before anything changes.

```json
{
  "id": "PRO-0001",
  "created_at": "2026-10-19T15:10:00+00:00",
  "created_by": "agent",
  "summary": "Accept the invoice total",
  "rationale": "Stated on the signed invoice (CLM-0001); the draft (CLM-0007) is superseded by it.",
  "reversal": "Apply a proposal returning CON-0001 to proposed.",
  "changes": [
    {
      "target": "CON-0001",
      "type": "conclusion",
      "base_revision": 1,
      "data": { "...": "the complete new data for r2" }
    }
  ]
}
```

`base_revision` is the revision the change was written against (0 creates a new record). If the record
has moved on, `tools/apply.py` refuses and a new proposal is needed.

## Decision draft, `drafts/decisions/<name>.json`

Written by the agent for the owner to review.

```json
{
  "statement": "Approve PRO-0001: accept 1,250.00 CAD as the total of Invoice 4471.",
  "responds_to": "Question in chat on 2026-10-19 about the invoice total",
  "approves": ["PRO-0001"],
  "propositions": [],
  "supersedes": [],
  "limits": "Does not decide whether the invoice was paid."
}
```

Use `propositions` instead of `approves` when the owner is settling a fact directly (for example from
their own knowledge). A conclusion then cites the decision in its `decisions` list.

## Decision (DEC), in `decisions/register.json`

Written only by `tools/decide.py`, which adds the owner's own words as `quote`, the time, and
`accepted` or `rejected`. The previous register is saved under `decisions/history/` first. Entries are
never edited or removed; a later decision lists the earlier one in `supersedes`, and any conclusion that
rested on the superseded decision then fails validation until a proposal revises it.

## Releases

`tools/release.py` freezes the project as `releases/NNN/`:

- `manifest.json`: the SHA-256 of every file in `raw/`, `records/`, `proposals/` and the register.
- `view.json`: the accepted conclusions with their quotes, sources and decisions.

`releases/current.json` points to the latest. After a release, validation fails if any listed file changes.
