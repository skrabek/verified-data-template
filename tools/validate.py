"""Check every rule the project depends on. Exits with status 1 when any error is found.

These checks cannot prove that a quote is accurate or that a conclusion is true. They prove that
every accepted value traces back to preserved originals and a human approval, and that nothing
preserved or released has changed since.

    python tools/validate.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import common as c

USES = {"eligible", "context", "excluded"}
CONCLUSION_STATUS = {"proposed", "accepted", "rejected", "superseded"}
CLAIM_KINDS = {"stated", "inferred"}
DECISION_STATUS = {"accepted", "rejected"}


def complete(proposition) -> bool:
    return isinstance(proposition, dict) and all(
        str(proposition.get(key, "")).strip() for key in ("subject", "predicate", "value"))


def same_question(a, b) -> bool:
    return isinstance(a, dict) and isinstance(b, dict) and all(
        a.get(key) == b.get(key) for key in ("subject", "predicate"))


def validate(root: Path) -> tuple[list[str], list[str]]:
    root = Path(root)
    errors: list[str] = []
    warnings: list[str] = []
    if not (root / "project.json").exists():
        return ["project.json is missing"], []
    try:
        cfg = c.config(root)
        records = c.load_records(root)
        proposals = c.load_proposals(root)
        register = c.load_register(root)
    except ValueError as error:
        return [str(error)], []
    zero_weight = set(cfg.get("zero_weight_classes", []))
    decisions = {d.get("id"): d for d in register}
    status = c.decision_status(register)

    # Decision register: each entry complete, and nothing earlier changed or removed.
    position = {}
    for index, decision in enumerate(register):
        identity = decision.get("id", f"entry {index + 1}")
        if identity in position:
            errors.append(f"{identity}: duplicate decision ID")
        position[identity] = index
        for field in ("recorded_at", "statement", "quote", "responds_to"):
            if not str(decision.get(field, "")).strip():
                errors.append(f"{identity}: decision needs {field}")
        if decision.get("status") not in DECISION_STATUS:
            errors.append(f"{identity}: status must be accepted or rejected")
        for proposal in decision.get("approves", []):
            if proposal not in proposals:
                errors.append(f"{identity}: approves unknown proposal {proposal}")
        for older in decision.get("supersedes", []):
            if position.get(older, index) >= index:
                errors.append(f"{identity}: can only supersede an earlier decision, not {older}")
        for proposition in decision.get("propositions", []):
            if not complete(proposition):
                errors.append(f"{identity}: each proposition needs subject, predicate and value")
    history = sorted((root / "decisions" / "history").glob("*/register.json"))
    for copy in history:
        for old in c.load_json(copy).get("decisions", []):
            if decisions.get(old.get("id")) != old:
                errors.append(f"{old.get('id')}: changed or removed since {c.rel(root, copy)}; "
                              "record a superseding decision instead")

    # Proposals.
    for identity, proposal in proposals.items():
        if proposal.get("id") != identity:
            errors.append(f"proposals/{identity}.json: id does not match the filename")
        for field in ("summary", "rationale", "reversal"):
            if not str(proposal.get(field, "")).strip():
                errors.append(f"{identity}: proposal needs {field}")
        if not proposal.get("changes"):
            errors.append(f"{identity}: proposal has no changes")
        for change in proposal.get("changes", []):
            target = str(change.get("target", ""))
            if c.TYPE_OF.get(target.split("-")[0]) != change.get("type"):
                errors.append(f"{identity}: target {target} does not match type {change.get('type')}")
            if not isinstance(change.get("base_revision"), int) or change["base_revision"] < 0:
                errors.append(f"{identity}: {target} needs base_revision (0 creates a new record)")

    # Records: revision history.
    for identity, revisions in records.items():
        kind = c.TYPE_OF.get(identity.split("-")[0])
        for expected, revision in enumerate(revisions, start=1):
            doc, where = revision["doc"], c.rel(root, revision["path"])
            if revision["n"] != expected:
                errors.append(f"{where}: revisions must run r1, r2, ... without gaps")
                break
            if (doc.get("id"), doc.get("type"), revision["folder"], doc.get("revision")) != (
                    identity, kind, kind, revision["n"]):
                errors.append(f"{where}: id, type, folder and revision number must agree")
            proposal_id = doc.get("applied_from")
            if revision["n"] > 1 and not proposal_id:
                errors.append(f"{where}: a revision after r1 must come from an approved proposal (tools/apply.py)")
            if proposal_id:
                proposal = proposals.get(proposal_id)
                change = next((ch for ch in (proposal or {}).get("changes", []) if ch.get("target") == identity), None)
                if proposal is None:
                    errors.append(f"{where}: applied from unknown proposal {proposal_id}")
                elif not c.approving_decision(register, proposal_id, include_superseded=True):
                    errors.append(f"{where}: {proposal_id} was never approved")
                elif change is None or change.get("base_revision") != revision["n"] - 1 or change.get("data") != doc.get("data"):
                    errors.append(f"{where}: does not match what {proposal_id} approved")

    # Records: rules for each type, on the current revision.
    referenced_objects = set()
    accepted_by_question: dict[tuple, set] = {}
    for identity, revisions in records.items():
        doc = revisions[-1]["doc"]
        data = doc.get("data") or {}
        kind = doc.get("type")
        where = c.rel(root, revisions[-1]["path"])

        if kind == "source":
            use, cls = data.get("use"), data.get("class")
            for field in ("title", "class", "provenance", "original_filename", "object", "sha256"):
                if not str(data.get(field, "")).strip():
                    errors.append(f"{where}: source needs {field}")
            if use not in USES:
                errors.append(f"{where}: use must be eligible, context or excluded")
            if cls in zero_weight and use == "eligible":
                errors.append(f"{where}: class '{cls}' carries no evidential weight (project.json); use must be context or excluded")
            if use != "eligible" and not str(data.get("use_reason", "")).strip():
                errors.append(f"{where}: a context or excluded source needs use_reason")
            path = root / str(data.get("object", ""))
            referenced_objects.add(c.rel(root, path) if path.is_file() else None)
            if not path.is_file():
                errors.append(f"{where}: preserved original {data.get('object')} is missing")
            elif c.sha256_file(path) != data.get("sha256"):
                errors.append(f"{where}: preserved original {data.get('object')} has changed")

        elif kind == "claim":
            if c.kind_of(records, data.get("source")) != "source":
                errors.append(f"{where}: claim must cite an existing source")
            for field in ("locator", "quote"):
                if not str(data.get(field, "")).strip():
                    errors.append(f"{where}: claim needs {field} (where in the source, and its exact words)")
            if not complete(data.get("proposition")):
                errors.append(f"{where}: claim needs a proposition with subject, predicate and value")
            if data.get("kind") not in CLAIM_KINDS:
                errors.append(f"{where}: claim kind must be stated or inferred")
            if data.get("kind") == "inferred" and not str(data.get("reasoning", "")).strip():
                errors.append(f"{where}: an inferred claim needs reasoning")

        elif kind == "conclusion":
            proposition = data.get("proposition")
            supporting = data.get("supporting_claims", [])
            contradicting = data.get("contradicting_claims", [])
            cited = data.get("decisions", [])
            if not complete(proposition):
                errors.append(f"{where}: conclusion needs a proposition with subject, predicate and value")
            if data.get("status") not in CONCLUSION_STATUS:
                errors.append(f"{where}: status must be one of {sorted(CONCLUSION_STATUS)}")
            for claim in supporting + contradicting:
                if c.kind_of(records, claim) != "claim":
                    errors.append(f"{where}: {claim} is not an existing claim")
            if set(supporting) & set(contradicting):
                errors.append(f"{where}: the same claim cannot both support and contradict")
            for claim in supporting:
                if (c.current(records, claim) or {}).get("proposition") != proposition:
                    errors.append(f"{where}: supporting claim {claim} states a different proposition")
            for claim in contradicting:
                if not same_question((c.current(records, claim) or {}).get("proposition"), proposition):
                    errors.append(f"{where}: contradicting claim {claim} is about a different subject or predicate")
            for decision_id in cited:
                decision = decisions.get(decision_id)
                if not decision or decision.get("status") != "accepted":
                    errors.append(f"{where}: {decision_id} is not an accepted decision")
                elif proposition not in decision.get("propositions", []):
                    errors.append(f"{where}: proposition is outside the scope of {decision_id}")
            if data.get("status") == "accepted":
                via_decision = any(status.get(d) == "accepted" and proposition in decisions[d].get("propositions", [])
                                   for d in cited if d in decisions)
                via_proposal = bool(doc.get("applied_from")) and c.approving_decision(
                    register, doc["applied_from"], include_superseded=True)
                if not via_decision and not via_proposal:
                    errors.append(f"{where}: accepted without human approval; cite a decision covering this "
                                  "proposition or apply an approved proposal")
                if not supporting and not cited:
                    errors.append(f"{where}: accepted conclusion has no basis (supporting claims or a decision)")
                for decision_id in cited:
                    if status.get(decision_id) == "superseded":
                        errors.append(f"{where}: rests on superseded decision {decision_id}; propose a revision")
                for claim in supporting:
                    source = c.current(records, (c.current(records, claim) or {}).get("source", "")) or {}
                    if source.get("use") != "eligible":
                        errors.append(f"{where}: supporting claim {claim} comes from a source that is not eligible evidence")
                if contradicting and not str(data.get("notes", "")).strip():
                    errors.append(f"{where}: accepted despite contradicting claims; notes must say why")
                if complete(proposition):
                    accepted_by_question.setdefault((proposition["subject"], proposition["predicate"]), set()).add(
                        proposition["value"])

        elif kind == "hypothesis":
            if not str(data.get("statement", "")).strip():
                errors.append(f"{where}: hypothesis needs a statement")
            for related in data.get("related", []):
                if related not in records:
                    errors.append(f"{where}: related record {related} does not exist")

    for (subject, predicate), values in accepted_by_question.items():
        if len(values) > 1:
            warnings.append(f"{subject} / {predicate} has {len(values)} accepted values; fine only if the predicate allows several")

    # Preserved originals.
    objects = root / "raw" / "objects"
    if objects.exists():
        for path in sorted(p for p in objects.rglob("*") if p.is_file() and not p.name.startswith(".")):
            if c.rel(root, path) not in referenced_objects:
                warnings.append(f"{c.rel(root, path)} is not referenced by any source")
            if os.access(path, os.W_OK):
                warnings.append(f"{c.rel(root, path)} is writable; originals should be read-only")

    # Releases: everything a release listed is still byte for byte the same.
    history_hashes = {c.sha256_file(copy) for copy in history}
    for manifest_path in sorted((root / "releases").glob("*/manifest.json")):
        manifest = c.load_json(manifest_path)
        for path, digest in manifest.get("files", {}).items():
            file = root / path
            if not file.is_file():
                errors.append(f"release {manifest.get('release')}: {path} is missing")
            elif c.sha256_file(file) != digest and not (path == "decisions/register.json" and digest in history_hashes):
                errors.append(f"release {manifest.get('release')}: {path} has changed since it was released")
    pointer = root / "releases" / "current.json"
    if pointer.exists() and not (root / "releases" / c.load_json(pointer).get("release", "") / "manifest.json").exists():
        errors.append("releases/current.json points to a release that does not exist")

    # Project-specific rules.
    local = root / "tools" / "local_rules.py"
    if local.exists():
        spec = importlib.util.spec_from_file_location("local_rules", local)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        more_errors, more_warnings = module.check({"root": root, "config": cfg, "records": records,
                                                   "proposals": proposals, "register": register})
        errors += more_errors
        warnings += more_warnings

    return errors, warnings


def main() -> int:
    errors, warnings = validate(c.ROOT)
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
