# Verified data project template

A starting point for any project where data must not change without evidence and a person's approval,
and where AI agents do much of the work. It is not tied to any subject; the examples use an invoice.

Use it for things like records research, contract or invoice extraction, compliance evidence, or
cataloguing: anywhere an agent reads documents and fills in data, and a wrong value must never quietly
become "the truth".

## The problem it solves

An AI agent can read a document, misread a number, and write it into your data with complete confidence.
It can repeat a guess in five places until it looks confirmed. It can "tidy up" a value that disagrees
with another, and lose the disagreement. Instructions alone ("be careful", "cite sources") reduce this
but don't prevent it.

This template makes those failures structurally hard and easy to detect:

1. **Originals are kept exactly.** Every file is copied once, named by its SHA-256 hash, and made read-only.
2. **Statements are claims, not facts.** A claim records what one source says, where, in its exact words.
3. **Only a person accepts facts.** A value becomes accepted only through a decision the owner types, in
   their own words, at a real terminal. Agents propose; they never decide.
4. **Nothing is overwritten.** Records gain numbered revisions, decisions are appended, and released files
   are locked by hash.
5. **Rules are enforced in code.** A validator, a Claude Code hook and tests catch what instructions miss.

## What it does, step by step

A worked example. You receive a signed invoice and an AI-written summary of it.

### 1. Preserve the originals: `tools/ingest.py`

```bash
python tools/ingest.py inbox/invoice-4471.pdf --title "Invoice 4471 (signed)" --class invoice --provenance "Emailed by supplier, 2026-10-18"
python tools/ingest.py inbox/summary.md --title "AI summary of 4471" --class ai_generated --use context --use-reason "AI-written; leads only"
```

For each file it:
- computes the SHA-256 hash and refuses if that exact file is already preserved;
- copies it to `raw/objects/sha256/<first two characters>/<hash>.<ext>` (the original is never moved);
- re-hashes the copy to verify it, then makes the copy read-only;
- writes a **source** record, `records/source/SRC-0001/r1.json`, saying what it is, where it came from,
  and whether it may count as evidence (`eligible`, `context` or `excluded`).

Source classes listed under `zero_weight_classes` in `project.json` (AI output, summaries, narratives)
can never be eligible evidence.

### 2. Record what the source says: claims

The agent writes `records/claim/CLM-0001/r1.json` (`python tools/new.py claim` gives the next free ID):

```json
{
  "source": "SRC-0001",
  "locator": "page 1, line 14",
  "quote": "Total due: $1,250.00 CAD",
  "proposition": { "subject": "Invoice 4471", "predicate": "total_amount", "value": "1,250.00 CAD" },
  "kind": "stated"
}
```

A claim is only "this source says this, here". Anything worked out (a converted currency, a calculated
date) is a separate claim with `"kind": "inferred"` and written reasoning.

### 3. Propose a conclusion

The agent writes a **conclusion** with status `proposed`, listing every supporting and contradicting
claim. If two sources disagree, both stay; nothing is silently resolved.

To make it accepted, the agent writes:
- a **proposal**, `proposals/PRO-0001.json`: the exact new record, the revision it applies to,
  a rationale and how to reverse it;
- a **decision draft**, `drafts/decisions/approve-PRO-0001.json`: what you are being asked to decide.

Then it stops and asks you.

### 4. You decide: `tools/decide.py`

```bash
python tools/decide.py drafts/decisions/approve-PRO-0001.json
```

It shows the draft, asks accept or reject, and asks for your decision in your own words. Then it:
- saves the current decision register under `decisions/history/<time>-before-DEC-0001/`;
- appends `DEC-0001` to `decisions/register.json` with your words stored verbatim, the time, and what
  it approves.

It refuses to run unless a person is at an interactive console. Piped input, an agent's shell, or a
null input device are all refused. Run it in PowerShell or Windows Terminal, or with `winpty` in Git Bash.

You can also decide a fact directly (for example from your own knowledge) by listing the exact
proposition in the draft's `propositions`; a conclusion can then cite that decision.

### 5. Apply what you approved: `tools/apply.py`

```bash
python tools/apply.py PRO-0001
```

It refuses unless an accepted decision approves the proposal, the proposal hasn't been applied before,
and each record is still at the revision the proposal was written against. It checks everything first,
then writes the next revision (`r2.json`) recording `applied_from` and `approved_by`. It never overwrites.

### 6. Check everything: `tools/validate.py`

```bash
python tools/validate.py
```

It reports errors (exit code 1) and warnings. It checks that:

- every preserved original still matches its hash;
- every claim has a source, a locator, a quote and a complete proposition, and inferred claims have reasoning;
- an accepted conclusion has your approval (a decision covering that exact proposition, or an approved
  proposal), has a basis, relies only on eligible sources, and explains itself when claims contradict it;
- supporting claims state exactly the same value, and contradicting claims are about the same question;
- revisions run r1, r2, … with no gaps, every revision after r1 came from an approved proposal, and its
  content is exactly what was approved;
- no earlier decision has been edited or removed (every history copy is compared with the live register);
- a conclusion resting on a decision you later superseded is flagged until it is revised;
- nothing listed in a release has changed;
- any extra rules you add in `tools/local_rules.py` pass.

### 7. Freeze a release: `tools/release.py`

```bash
python tools/release.py "Invoices received in October"
```

It refuses if validation fails. Otherwise it writes `releases/NNN/manifest.json` (the hash of every
original, record, proposal and the register), and `releases/NNN/view.json` (every accepted value with
its quotes, sources and decisions). It makes both read-only and points `releases/current.json` at them.

### 8. Ask why: `tools/explain.py`

```bash
python tools/explain.py CON-0001
```

It prints the full chain: the accepted value, each supporting and contradicting quote with its locator
and source file, your decision in your words, and the proposal it came from.

## How AI agents are kept in line

There are three layers, from softest to hardest:

1. **Rules they read.** `AGENTS.md` (read by most agent tools) and `CLAUDE.md` (which loads it for Claude
   Code) say what the agent must never do, what it must always do, and to ask when unsure.
2. **A hook that blocks actions** (Claude Code only). `.claude/hooks/guard.py` runs before every file edit
   and shell command. It **denies** writes to `raw/`, `releases/`, `decisions/` and released records. It
   **asks you** before anyone edits the rules themselves (`tools/`, `tests/`, `AGENTS.md`, `CLAUDE.md`,
   `project.json`, `.claude/`). If the hook itself crashes, it blocks the action rather than allowing it.
3. **Checks that catch anything that got through.** The validator and hashes detect any change after the
   fact, whichever tool or person made it.

| Rule | Instructions | Hook | Validator / tool |
|---|---|---|---|
| Originals never change | yes | denies writes to `raw/` | hash check on every source |
| Released data never changes | yes | denies edits to released records and `releases/` | manifest hash check |
| Only the owner decides | yes | denies writes to `decisions/` | `decide.py` requires a real console |
| Decisions are never rewritten | yes | denies writes to `decisions/` | history copies must still match |
| Accepted values need approval and evidence | yes | | conclusion checks |
| Weak sources can't support facts | yes | | zero-weight classes, eligible-source check |
| Changes match what was approved | yes | | `apply.py` base-revision check; data comparison |
| The rules can't be quietly weakened | yes | asks before editing rule files | tests |

## Getting started

Requires Python 3.10 or later (standard library only). Git is strongly recommended.

1. Click **Use this template** on GitHub, or copy the folder.
2. Edit `project.json`: project name, owner, the source classes that must never count as evidence, and
   (optionally) the allowed predicates.
3. Run the tests and the validator:
   ```bash
   python -m unittest discover tests
   ```
   ```bash
   python tools/validate.py
   ```
4. Back up the project somewhere else. A hash shows that something changed; it does not restore it.
5. If you use Claude Code, open the project and ask it to edit a file under `raw/`. The hook should refuse.

## Folder layout

```text
AGENTS.md            Rules every agent follows
CLAUDE.md            Loads AGENTS.md for Claude Code, plus hook notes
project.json         Settings: zero-weight source classes, allowed predicates
.claude/             Claude Code settings and the guard hook
docs/data-model.md   Every record type and field, with examples
raw/objects/sha256/  Preserved originals (read-only, written by ingest.py)
records/             source, claim, conclusion, hypothesis records; one folder per ID, one file per revision
proposals/           Proposed changes, written before anything changes
drafts/decisions/    Decision drafts for the owner
decisions/           register.json and history/ (every earlier version)
releases/            Frozen releases: hash manifest and accepted-value view
tools/               ingest, validate, apply, decide, release, explain, new, local_rules
tests/               Tests that break each rule and check it is caught
```

## Adapting it

- **Vocabulary.** Set `zero_weight_classes` and `predicates` in `project.json`. Keep subject names stable.
- **Domain rules.** Add checks to `tools/local_rules.py` (value formats, allowed values, which source
  classes may support which predicates), each with a test.
- **Standing policies.** Record general rules as decisions too, such as "a signed contract outranks an
  email", so each has your words and a date.
- **Other agent tools.** They read `AGENTS.md` but not the Claude Code hook, so run the validator in CI
  (included in `.github/workflows/`) or a git pre-commit hook.
- **Extra safety.** Make `raw/` read-only at the operating-system level and keep an off-machine backup.

## Limits

- The validator checks structure and traceability, not truth. It cannot tell whether a quote matches the
  page; your review against the preserved original is that check.
- The hook's shell-command detection is a heuristic, which is why every protected file is also hash-checked.
- IDs are allocated by counting existing files, so work with one writer at a time.
- `project.json` is not hash-locked. Record changes to it as decisions.
- In a public repository, everything you commit, including originals in `raw/`, is public. Keep real
  project data in a private repository.

## License

MIT. See [LICENSE](LICENSE).
