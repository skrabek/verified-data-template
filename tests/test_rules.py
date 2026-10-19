"""Each test breaks one rule on purpose and checks that it is caught.

    python -m unittest discover tests
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TEMPLATE / "tools"))

import common as c  # noqa: E402
from apply import apply  # noqa: E402
from decide import record  # noqa: E402
from ingest import ingest  # noqa: E402
from release import release  # noqa: E402
from validate import validate  # noqa: E402

TOTAL = {"subject": "Invoice 4471", "predicate": "total_amount", "value": "1,250.00 CAD"}


def make_writable(function, path, _):
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    function(path)


class Project(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.root = self.temp / "project"
        self.root.mkdir()
        shutil.copy(TEMPLATE / "project.json", self.root)
        (self.root / "decisions").mkdir()
        (self.root / "decisions" / "register.json").write_text('{"decisions": []}\n', encoding="utf-8")
        for folder in ("raw", "records", "proposals", "drafts/decisions"):
            (self.root / folder).mkdir(parents=True)
        self.inbox = self.temp / "inbox"
        self.inbox.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp, onexc=make_writable) if sys.version_info >= (3, 12) else \
            shutil.rmtree(self.temp, onerror=make_writable)

    # helpers
    def errors(self):
        return validate(self.root)[0]

    def assertError(self, fragment):
        errors = self.errors()
        self.assertTrue(any(fragment in e for e in errors), f"expected '{fragment}' in {errors}")

    def source(self, name="invoice.txt", text="Total due: $1,250.00 CAD", **options):
        file = self.inbox / name
        file.write_text(text, encoding="utf-8")
        args = {"title": name, "cls": "invoice", "provenance": "test"} | options
        return ingest(self.root, file, **args)

    def write(self, kind, data, identity=None, revision=1):
        identity = identity or c.next_id(self.root, c.PREFIX[kind])
        c.write_new(self.root / "records" / kind / identity / f"r{revision}.json", {
            "id": identity, "type": kind, "revision": revision, "created_at": c.now(),
            "created_by": "test", "applied_from": None, "data": data})
        return identity

    def claim(self, source, proposition=TOTAL):
        return self.write("claim", {"source": source, "locator": "line 1", "quote": "Total due: $1,250.00 CAD",
                                    "proposition": proposition, "kind": "stated", "reasoning": ""})

    def conclusion(self, status="proposed", supporting=(), decisions=(), contradicting=(), notes=""):
        return self.write("conclusion", {"proposition": TOTAL, "status": status, "supporting_claims": list(supporting),
                                         "contradicting_claims": list(contradicting), "decisions": list(decisions),
                                         "notes": notes})

    def decide(self, quote="Yes, that total is right", **draft):
        path = self.root / "drafts" / "decisions" / f"draft-{len(list((self.root / 'drafts' / 'decisions').iterdir()))}.json"
        path.write_text(json.dumps({"statement": "test decision", "responds_to": "test"} | draft), encoding="utf-8")
        return record(self.root, path, quote, "accepted")["id"]

    def propose(self, target, data, base_revision):
        identity = c.next_id(self.root, "PRO")
        c.write_new(self.root / "proposals" / f"{identity}.json", {
            "id": identity, "created_at": c.now(), "created_by": "test", "summary": "s", "rationale": "r",
            "reversal": "revert", "changes": [{"target": target, "type": "conclusion",
                                               "base_revision": base_revision, "data": data}]})
        return identity


class Rules(Project):
    def test_empty_project_is_valid(self):
        self.assertEqual(self.errors(), [])

    def test_ingest_preserves_read_only_copy_and_refuses_duplicates(self):
        identity = self.source()
        data = c.current(c.load_records(self.root), identity)
        self.assertFalse(os.access(self.root / data["object"], os.W_OK))
        with self.assertRaises(SystemExit):
            self.source()
        self.assertEqual(self.errors(), [])

    def test_changed_original_is_caught(self):
        identity = self.source()
        data = c.current(c.load_records(self.root), identity)
        path = self.root / data["object"]
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        path.write_text("Total due: $9,999.00 CAD", encoding="utf-8")
        self.assertError("has changed")

    def test_claim_needs_quote_and_locator(self):
        self.write("claim", {"source": self.source(), "locator": "", "quote": "",
                             "proposition": TOTAL, "kind": "stated"})
        self.assertError("claim needs locator")

    def test_proposed_conclusion_is_fine(self):
        self.conclusion(supporting=[self.claim(self.source())])
        self.assertEqual(self.errors(), [])

    def test_agent_cannot_accept_on_its_own(self):
        self.conclusion("accepted", supporting=[self.claim(self.source())])
        self.assertError("accepted without human approval")

    def test_owner_decision_can_accept_a_proposition(self):
        claim = self.claim(self.source())
        decision = self.decide(propositions=[TOTAL])
        self.conclusion("accepted", supporting=[claim], decisions=[decision])
        self.assertEqual(self.errors(), [])

    def test_decision_scope_is_exact(self):
        decision = self.decide(propositions=[TOTAL | {"value": "1,520.00 CAD"}])
        self.conclusion("accepted", decisions=[decision])
        self.assertError("outside the scope")

    def test_zero_weight_source_cannot_be_eligible(self):
        self.source("summary.md", "AI summary", cls="ai_generated")
        self.assertError("carries no evidential weight")

    def test_context_source_cannot_support_accepted_value(self):
        claim = self.claim(self.source("summary.md", "AI summary", cls="ai_generated", use="context",
                                       use_reason="AI-written"))
        self.conclusion("accepted", supporting=[claim], decisions=[self.decide(propositions=[TOTAL])])
        self.assertError("not eligible evidence")

    def test_supporting_claim_must_state_the_same_value(self):
        claim = self.claim(self.source(), TOTAL | {"value": "1,520.00 CAD"})
        self.conclusion(supporting=[claim])
        self.assertError("states a different proposition")

    def test_contradictions_need_an_explanation(self):
        source = self.source()
        good = self.claim(source)
        bad = self.claim(self.source("draft.txt", "Total: 1,520"), TOTAL | {"value": "1,520.00 CAD"})
        self.conclusion("accepted", supporting=[good], contradicting=[bad], decisions=[self.decide(propositions=[TOTAL])])
        self.assertError("notes must say why")

    def test_proposal_path_and_tampering_after_apply(self):
        con = self.conclusion(supporting=[self.claim(self.source())])
        data = c.current(c.load_records(self.root), con) | {"status": "accepted"}
        proposal = self.propose(con, data, 1)
        with self.assertRaises(SystemExit):
            apply(self.root, proposal)  # not approved yet
        self.decide(approves=[proposal])
        apply(self.root, proposal)
        self.assertEqual(self.errors(), [])
        with self.assertRaises(SystemExit):
            apply(self.root, proposal)  # only once
        revision = self.root / "records" / "conclusion" / con / "r2.json"
        doc = json.loads(revision.read_text(encoding="utf-8"))
        doc["data"]["proposition"] = TOTAL | {"value": "1,520.00 CAD"}
        revision.write_text(json.dumps(doc), encoding="utf-8")
        self.assertError("does not match what")

    def test_stale_proposal_is_refused(self):
        con = self.conclusion(supporting=[self.claim(self.source())])
        data = c.current(c.load_records(self.root), con)
        first, second = self.propose(con, data | {"notes": "a"}, 1), self.propose(con, data | {"notes": "b"}, 1)
        self.decide(approves=[first, second])
        apply(self.root, first)
        with self.assertRaises(SystemExit):
            apply(self.root, second)

    def test_revision_without_proposal_is_caught(self):
        con = self.conclusion()
        self.write("conclusion", c.current(c.load_records(self.root), con), identity=con, revision=2)
        self.assertError("must come from an approved proposal")

    def test_rewritten_decision_is_caught(self):
        self.decide(propositions=[TOTAL])
        self.decide(propositions=[TOTAL])  # saves a history copy containing the first decision
        register = self.root / "decisions" / "register.json"
        data = json.loads(register.read_text(encoding="utf-8"))
        data["decisions"][0]["quote"] = "something the owner never said"
        register.write_text(json.dumps(data), encoding="utf-8")
        self.assertError("changed or removed")

    def test_superseded_decision_reopens_the_conclusion(self):
        first = self.decide(propositions=[TOTAL])
        self.conclusion("accepted", decisions=[first])
        self.assertEqual(self.errors(), [])
        self.decide("No, that was wrong", supersedes=[first])
        self.assertError("rests on superseded decision")

    def test_release_locks_files(self):
        self.conclusion(supporting=[self.claim(self.source())])
        number = release(self.root, "first")
        self.decide(propositions=[TOTAL])  # the register may grow after a release
        self.assertEqual(self.errors(), [])
        claim = next((self.root / "records" / "claim").glob("*/r1.json"))
        claim.write_text(claim.read_text(encoding="utf-8").replace("line 1", "line 2"), encoding="utf-8")
        self.assertError(f"release {number}")


class Guard(unittest.TestCase):
    """The Claude Code hook, run the way Claude Code runs it."""

    def run_guard(self, tool, **tool_input):
        result = subprocess.run([sys.executable, str(TEMPLATE / ".claude" / "hooks" / "guard.py")],
                                input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
                                capture_output=True, text=True, env=os.environ | {"CLAUDE_PROJECT_DIR": str(TEMPLATE)})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] if result.stdout.strip() else "allow"

    def test_file_tools(self):
        self.assertEqual(self.run_guard("Write", file_path=str(TEMPLATE / "raw" / "x.txt")), "deny")
        self.assertEqual(self.run_guard("Edit", file_path="decisions/register.json"), "deny")
        self.assertEqual(self.run_guard("Write", file_path="releases/001/view.json"), "deny")
        self.assertEqual(self.run_guard("Edit", file_path="tools/validate.py"), "ask")
        self.assertEqual(self.run_guard("Write", file_path="records/claim/CLM-0001/r1.json"), "allow")
        self.assertEqual(self.run_guard("Write", file_path="proposals/PRO-0001.json"), "allow")

    def test_shell(self):
        self.assertEqual(self.run_guard("Bash", command="rm -rf raw/objects"), "deny")
        self.assertEqual(self.run_guard("PowerShell", command="Remove-Item decisions\\register.json"), "deny")
        self.assertEqual(self.run_guard("Bash", command="echo x > records/claim/CLM-0001/r1.json"), "deny")
        self.assertEqual(self.run_guard("Bash", command="python tools/ingest.py inbox/a.pdf --title a"), "allow")
        self.assertEqual(self.run_guard("Bash", command="python tools/validate.py; rm -rf raw/"), "deny")
        self.assertEqual(self.run_guard("Bash", command="cat records/claim/CLM-0001/r1.json"), "allow")


if __name__ == "__main__":
    unittest.main()
