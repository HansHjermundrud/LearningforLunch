#!/usr/bin/env python3
"""Regression suite for the learning system.

Every test runs the scripts in a fresh temporary root with its own config
(notes, reviews, exercises and state all under that root) and an injected clock
(LEARN_NOW). Nothing here can touch the configured real vault or live state.

Run:  python3 -m unittest discover -s scripts/tests -p 'test_*.py'
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
NOW = "2026-09-25T15:00:00+02:00"

PLAN3 = {"nodes": [
    {"id": "n1", "label": "All communication is packets", "depends": []},
    {"id": "n2", "label": "Packets get lost", "depends": []},
    {"id": "n3", "label": "Reliability built on top", "depends": ["n1"]},
]}

PREP_N1 = {
    "objective": "explain that every transfer is a sequence of packets",
    "claims": [{"id": "c1", "kind": "definition", "text": "a packet is the unit of transfer"}],
    "misconceptions": [{"id": "m1", "text": "the network carries a continuous stream", "repair": "two-packet trace"}],
    "checks": [
        {"id": "q1", "type": "short", "role": "normal", "load_bearing": True, "review": True,
         "variants": [
             {"id": "v1", "question": "Why can two consecutive bytes arrive out of order?", "answer": "different packets, different paths",
              "required": ["different packets", "independent routing"]},
             {"id": "v2", "question": "A file arrives with its middle missing for a moment. Why is that possible?", "answer": "packets travel independently",
              "required": ["different packets"]}],
         "hints": ["What does the network forward?", "Is one message one thing on the wire?", "Two packets, two paths."]},
        {"id": "q2", "type": "mcq", "role": "fresh",
         "variants": [{"id": "v1", "question": "What does a router forward?", "options": ["Whole files", "Packets", "Byte streams", "I don't know"], "answer": "Packets"}]},
    ],
    "status": "ready",
}

TOPIC_PREP = {
    "capability": "explain why TCP is reliable",
    "chunks": [{"id": "s1", "label": "basics", "nodes": ["n1", "n2", "n3"]}],
    "exit_criteria": [{"id": "x1", "text": "explain loss recovery", "nodes": ["n3"], "checks": [
        {"id": "xq1", "type": "short", "role": "exit", "variants": [
            {"id": "v1", "question": "How does TCP recover a lost segment?", "answer": "retransmit", "required": ["sender retransmits"]}]}]}],
    "sources": [{"id": "rfc9293", "url": "https://www.rfc-editor.org/rfc/rfc9293", "title": "TCP"}],
}

LEGACY_STATE = {
    "version": 1, "active_topic": "old", "log_target": None,
    "topics": {"old": {
        "title": "Old topic", "started": "2026-09-20", "updated": "2026-09-21T10:00:00+02:00", "finished": None, "status": "teaching",
        "goal": "g", "note": None, "edge": ["e1"],
        "plan": {"approved": True, "mermaid": "", "nodes": [
            {"id": "n1", "label": "A", "depends": [], "why": "", "status": "done", "check": "short", "summary": "landed", "done_at": "2026-09-20T12:00:00+02:00"},
            {"id": "n2", "label": "B", "depends": ["n1"], "why": "", "status": "shaky", "check": "mcq", "summary": "confused"},
            {"id": "n3", "label": "C", "depends": ["n2"], "why": "", "status": "pending", "check": "", "summary": ""}]},
        "next": "repair n2", "log": [{"ts": "2026-09-21T10:00:00+02:00", "event": "node-shaky", "text": "n2"}]}},
}

LEGACY_DECK = {"version": 1, "cards": [
    {"id": "cu1dsb", "topic": "old", "node": "n1", "type": "mcq", "question": "Q1?", "answer": "A", "key_points": [],
     "options": ["A", "B", "I don't know"], "task": "", "created": "2026-09-20", "due": "2026-09-22", "interval": 1, "ease": 1.64,
     "reps": 0, "lapses": 2, "history": [{"date": "2026-09-20", "q": 1, "note": "chose B"}, {"date": "2026-09-21", "q": 2, "note": ""}],
     "suspended": False, "points": "p is shared; prose explanation that was stored under the wrong key"},
    {"id": "c3kqx8", "topic": "old", "node": "n1", "type": "short", "question": "Q2?", "answer": "A2",
     "key_points": ["each thread has its own p|only thread 0's p is set", "thread 0 prints 0"], "options": [], "task": "",
     "created": "2026-09-20", "due": "2026-09-27", "interval": 6, "ease": 2.5, "reps": 2, "lapses": 0,
     "history": [{"date": "2026-09-20", "q": 4, "note": ""}, {"date": "2026-09-21", "q": 5, "note": ""}], "suspended": False},
]}


class Base(unittest.TestCase):
    """A fresh repo-like root per test, scripts copied in, config pointing inside it."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="learn-test-"))
        shutil.copytree(SCRIPTS, self.root / "scripts", ignore=shutil.ignore_patterns("tests", "__pycache__"))
        self.vault = self.root / "vault"
        self.config = {
            "notesDir": str(self.vault / "notes"), "vizDir": str(self.vault / "viz"), "reviewsDir": str(self.vault / "reviews"),
            "exercisesDir": "exercises", "stateDir": "state", "timezone": "Europe/Oslo", "checkpointMinutes": 12, "reviewMinutes": 10,
        }
        (self.root / "learn.config.json").write_text(json.dumps(self.config), "utf-8")
        self.now = NOW

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- helpers ---------------------------------------------------------------
    def env(self, now=None):
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(self.root)
        env["LEARN_NOW"] = now or self.now
        env.pop("PYTHONPATH", None)
        return env

    def cmd(self, script, *args, stdin=None, expect=0, now=None, timeout=120):
        res = subprocess.run([sys.executable, str(self.root / "scripts" / script), *map(str, args)], input=stdin,
                             capture_output=True, text=True, cwd=self.root, env=self.env(now), timeout=timeout)
        if expect is not None:
            self.assertEqual(res.returncode, expect, f"{script} {args}\nstdout: {res.stdout}\nstderr: {res.stderr}")
        return res

    def state(self, *args, stdin=None, expect=0, now=None):
        return self.cmd("state.py", *args, stdin=stdin, expect=expect, now=now)

    def srs(self, *args, stdin=None, expect=0, now=None):
        return self.cmd("srs.py", *args, stdin=stdin, expect=expect, now=now)

    def py(self, code, now=None, expect=0):
        """Run a snippet with the library importable (for library-level tests)."""
        pre = f"import sys; sys.path.insert(0, {str(self.root / 'scripts')!r})\n"
        res = subprocess.run([sys.executable, "-c", pre + textwrap.dedent(code)], capture_output=True, text=True,
                             cwd=self.root, env=self.env(now), timeout=60)
        if expect is not None:
            self.assertEqual(res.returncode, expect, f"snippet failed\nstdout: {res.stdout}\nstderr: {res.stderr}")
        return res

    def state_json(self):
        return json.loads((self.root / "state" / "state.json").read_text("utf-8"))

    def deck_json(self):
        return json.loads((self.root / "state" / "deck.json").read_text("utf-8"))

    def topic(self, slug="tcp-reliability"):
        return self.state_json()["topics"][slug]

    def node(self, nid, slug="tcp-reliability"):
        return next(n for n in self.topic(slug)["plan"]["nodes"] if n["id"] == nid)

    def start_lesson(self, plan=PLAN3, prep=True, topic_prep=True):
        self.state("start", "TCP reliability", "--goal", "understand reliability")
        self.state("plan-set", stdin=json.dumps(plan))
        self.state("plan-approve")
        if topic_prep:
            self.state("prep-topic", stdin=json.dumps(TOPIC_PREP))
        if prep:
            self.state("prep-node", "n1", stdin=json.dumps(PREP_N1))

    def record(self, data, expect=0, now=None):
        return self.state("record", stdin=json.dumps(data), expect=expect, now=now)

    def adhoc(self, node, question="Q?", required=("r1",), kind=None, review=False):
        q = {"type": "short", "question": question, "answer": "A", "required": list(required), "review": review}
        args = ["ask", node, "--adhoc"] + (["--kind", kind] if kind else [])
        return self.state(*args, stdin=json.dumps(q))


# --- 1. migration -------------------------------------------------------------------

class TestMigration(Base):
    def write_legacy(self):
        (self.root / "state").mkdir()
        (self.root / "state" / "state.json").write_text(json.dumps(LEGACY_STATE, indent=1), "utf-8")
        (self.root / "state" / "deck.json").write_text(json.dumps(LEGACY_DECK, indent=1), "utf-8")

    def test_legacy_migrates_twice_without_change_or_loss(self):
        self.write_legacy()
        raw_state = (self.root / "state" / "state.json").read_bytes()
        raw_deck = (self.root / "state" / "deck.json").read_bytes()
        out = self.state("migrate").stdout
        self.assertIn("v1 -> v2", out)
        backups = list((self.root / "state" / "backups").glob("*.bak"))
        self.assertEqual(len(backups), 2)
        self.assertEqual({b.read_bytes() for b in backups}, {raw_state, raw_deck}, "backups must be byte-for-byte")
        s1, d1 = self.state_json(), self.deck_json()
        self.assertEqual(s1["version"], 2)
        nodes = {n["id"]: n for n in s1["topics"]["old"]["plan"]["nodes"]}
        self.assertEqual((nodes["n1"]["coverage"], nodes["n1"]["readiness"], nodes["n1"]["legacy_status"]), ("covered", "unknown", "done"))
        self.assertEqual((nodes["n2"]["coverage"], nodes["n2"]["readiness"]), ("covered", "needs_repair"))
        self.assertEqual((nodes["n3"]["coverage"], nodes["n3"]["readiness"]), ("pending", "unknown"))
        self.assertEqual(nodes["n1"]["summary"], "landed")
        self.assertEqual(nodes["n1"]["status"], "done")  # legacy mirror kept
        cards = {c["id"]: c for c in d1["cards"]}
        self.assertEqual(len(cards["cu1dsb"]["history"]), 2)
        self.assertEqual(cards["cu1dsb"]["history"][0]["note"], "chose B")
        self.assertNotIn("points", cards["cu1dsb"])
        self.assertTrue(cards["cu1dsb"]["explanation"].startswith("p is shared"))
        self.assertEqual(cards["c3kqx8"]["key_points"], ["each thread has its own p", "only thread 0's p is set", "thread 0 prints 0"])
        self.assertEqual([h["kind"] for h in cards["c3kqx8"]["history"]], ["initial", "review"])
        self.assertTrue(all(h["valid"] for h in cards["c3kqx8"]["history"]))
        self.assertEqual(cards["c3kqx8"]["ease"], 2.5)  # scheduling fields untouched
        out2 = self.state("migrate").stdout
        self.assertIn("nothing to do", out2)
        self.assertEqual(self.state_json(), s1)
        self.assertEqual(self.deck_json(), d1)
        self.assertEqual(len(list((self.root / "state" / "backups").glob("*.bak"))), 2)

    def test_legacy_is_migrated_in_memory_for_reads_and_on_first_write(self):
        self.write_legacy()
        out = self.state("show", "--full").stdout
        self.assertIn("unverified legacy 1", out)
        self.assertEqual(json.loads((self.root / "state" / "state.json").read_text())["version"], 1)  # read did not write
        self.state("checkpoint", "hello")
        self.assertEqual(self.state_json()["version"], 2)
        self.assertTrue(list((self.root / "state" / "backups").glob("state.json.*premigration*.bak")))


# --- 2. corrupt files -----------------------------------------------------------------

class TestCorruption(Base):
    def test_corrupt_deck_blocks_writes_and_is_preserved(self):
        self.start_lesson(prep=False, topic_prep=False)
        deck = self.root / "state" / "deck.json"
        deck.write_bytes(b'{"version": 2, "cards": [ oops')
        raw = deck.read_bytes()
        res = self.srs("add", "--topic", "t", "--type", "short", "--q", "q", "--a", "a", "--points", "p", expect=1)
        self.assertIn("not valid JSON", res.stderr)
        self.assertIn("restore", res.stderr)
        self.assertEqual(deck.read_bytes(), raw)
        res = self.state("checkpoint", "x", expect=1)
        self.assertIn("deck.json", res.stderr)
        self.assertEqual(deck.read_bytes(), raw)
        hook = self.cmd("hook_session_start.py", stdin='{"source":"startup"}')
        self.assertIn("deck unavailable", json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(deck.read_bytes(), raw)

    def test_corrupt_state_blocks_writes_hooks_stay_usable(self):
        self.start_lesson(prep=False, topic_prep=False)
        path = self.root / "state" / "state.json"
        path.write_text("{not json", "utf-8")
        raw = path.read_bytes()
        self.state("checkpoint", "x", expect=1)
        self.assertEqual(path.read_bytes(), raw)
        hook = self.cmd("hook_session_start.py", stdin='{"source":"startup"}')
        ctx = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("STATE PROBLEM", ctx)
        stop = self.cmd("hook_stop_checkpoint.py", stdin='{"session_id":"x"}')
        self.assertEqual(stop.returncode, 0)
        self.assertEqual(path.read_bytes(), raw)

    def test_missing_files_initialise_safely(self):
        self.state("show")
        self.srs("stats")
        self.assertFalse((self.root / "state" / "state.json").exists())


# --- 3. plan validation ---------------------------------------------------------------------

class TestPlanValidation(Base):
    def setUp(self):
        super().setUp()
        self.state("start", "T", "--goal", "g")
        self.before = (self.root / "state" / "state.json").read_bytes()

    def reject(self, plan, text):
        res = self.state("plan-set", stdin=json.dumps(plan), expect=1)
        self.assertIn(text, res.stderr)
        self.assertEqual((self.root / "state" / "state.json").read_bytes(), self.before, "state must not change")

    def test_unknown_dependency(self):
        self.reject({"nodes": [{"id": "n1", "label": "a", "depends": ["nope"]}]}, "unknown node")

    def test_duplicate_id(self):
        self.reject({"nodes": [{"id": "n1", "label": "a"}, {"id": "n1", "label": "b"}]}, "duplicate node id")

    def test_cycle(self):
        self.reject({"nodes": [{"id": "n1", "label": "a", "depends": ["n2"]}, {"id": "n2", "label": "b", "depends": ["n1"]}]}, "cycle")

    def test_self_dependency_and_bad_status(self):
        self.reject({"nodes": [{"id": "n1", "label": "a", "depends": ["n1"]}]}, "depends on itself")
        self.reject({"nodes": [{"id": "n1", "label": "a", "status": "finished"}]}, "status must be")

    def test_node_add_with_unknown_dependency_is_rejected(self):
        self.state("plan-set", stdin=json.dumps(PLAN3))
        before = (self.root / "state" / "state.json").read_bytes()
        self.state("node-add", "n4", "x", "--depends", "n9", expect=1)
        self.assertEqual((self.root / "state" / "state.json").read_bytes(), before)


# --- 4-7. dependency and completion rules -------------------------------------------------------

class TestScheduling(Base):
    def test_shaky_prerequisite_blocks_dependent_but_not_independent(self):
        self.start_lesson(prep=False)
        self.state("node-shaky", "n1", "confuses loss with corruption")
        out = self.state("node-done", "n2", "derived unaided").stdout
        self.assertNotIn("Teach n3", out)
        self.assertIn("Repair n1", out)
        nxt = self.state("next-node").stdout
        self.assertIn("Blocked: n3 waits on n1 needs repair", nxt)
        # before n2 was covered it was eligible even though n1 needs repair
        self.assertIn("Needs repair: n1", nxt)

    def test_independent_node_stays_eligible_while_another_needs_repair(self):
        self.start_lesson(prep=False)
        self.state("node-shaky", "n1", "x")
        nxt = self.state("next-node").stdout
        self.assertIn("Eligible now: n2", nxt)
        self.assertIn("Teach n2", nxt)

    def test_finish_requires_required_coverage_and_exit_evidence(self):
        self.start_lesson(prep=False)
        res = self.state("finish", expect=1)
        self.assertIn("not taught", res.stderr)
        for n in ("n1", "n2", "n3"):
            self.adhoc(n)
            self.record({"result": "pass", "quality": 5})
        res = self.state("finish", expect=1)
        self.assertIn("exit criterion x1", res.stderr)
        self.assertEqual(self.topic()["status"], "teaching")
        self.state("ask", "n3", "--exit", "x1")
        self.record({"result": "pass", "quality": 5})
        self.state("finish", "--summary", "ok")
        self.assertEqual(self.topic()["status"], "finished")

    def test_finish_refuses_without_exit_criteria(self):
        self.start_lesson(prep=False, topic_prep=False)
        for n in ("n1", "n2", "n3"):
            self.adhoc(n)
            self.record({"result": "pass", "quality": 5})
        res = self.state("finish", expect=1)
        self.assertIn("no exit criteria", res.stderr)

    def test_optional_node_does_not_block_completion(self):
        self.start_lesson(prep=False)
        self.state("scope", "n2", "--optional", "--reason", "learner reduced scope")
        for n in ("n1", "n3"):
            self.adhoc(n)
            self.record({"result": "pass", "quality": 5})
        self.state("ask", "n3", "--exit", "x1")
        self.record({"result": "pass", "quality": 5})
        self.assertIn("finish", self.topic()["next"])
        self.state("finish")
        self.assertEqual(self.node("n2")["coverage"], "pending")

    def test_stop_records_no_mastery(self):
        self.start_lesson(prep=False)
        self.state("stop", "--summary", "out of time")
        self.assertEqual(self.topic()["status"], "stopped")
        self.assertIsNone(self.topic()["finished"])

    def test_node_done_ready_needs_recorded_evidence(self):
        self.start_lesson(prep=False)
        res = self.state("node-done", "n1", "summary", "--readiness", "ready", expect=1)
        self.assertIn("no independent passing attempt", res.stderr)
        self.state("node-done", "n1", "summary")
        self.assertEqual(self.node("n1")["readiness"], "provisional")


# --- 8-10. pending interactions -----------------------------------------------------------------

class TestPending(Base):
    def test_pending_question_survives_restart_with_same_variant_and_rubric(self):
        self.start_lesson()
        out = self.state("ask", "n1", "--fresh").stdout
        p = self.topic()["pending"]
        self.assertEqual((p["check"], p["variant"], p["rubric_version"], p["stage"]), ("q2", "v1", 1, "awaiting"))
        again = self.state("pending").stdout  # a fresh process: nothing in memory
        self.assertIn("What does a router forward?", again)
        self.assertIn("awaiting", again)
        # option order is stable across restarts
        opts = [l for l in out.splitlines() if l[:2] in ("A)", "B)", "C)", "D)")]
        opts2 = [l for l in again.splitlines() if l[:2] in ("A)", "B)", "C)", "D)")]
        self.assertEqual(opts, opts2)
        self.assertEqual(opts[-1], "D) I don't know")
        self.assertNotIn("Packets\n", again.split("-- grading key")[0] if "-- grading key" in again else "x")

    def test_pending_key_hidden_until_recorded(self):
        self.start_lesson()
        self.state("ask", "n1")
        out = self.state("pending").stdout
        self.assertNotIn("grading key", out)
        self.assertNotIn("different packets, different paths", out)
        self.state("answer", "separate packets")
        out = self.state("pending").stdout
        self.assertIn("grading key", out)
        self.assertIn("Recorded answer", out)

    def test_recorded_answer_resumes_grading_not_a_new_question(self):
        self.start_lesson()
        self.state("ask", "n1")
        self.state("answer", "they went as separate packets")
        res = self.state("ask", "n1", expect=1)
        self.assertIn("still recorded", res.stderr)
        self.assertEqual(self.topic()["pending"]["stage"], "recorded")
        hook = json.loads(self.cmd("hook_session_start.py", stdin='{"source":"compact"}').stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("NOT yet graded", hook)
        self.record({"result": "pass", "quality": 5})
        self.assertEqual(self.topic()["pending"]["stage"], "completed")
        self.assertEqual(len(self.topic()["attempts"]), 1)
        self.assertEqual(self.topic()["attempts"][0]["response"], "they went as separate packets")

    def test_replaying_record_and_grade_is_a_noop(self):
        self.start_lesson()
        self.state("ask", "n1")
        data = {"op": "op-1", "result": "pass", "quality": 5}
        self.record(data)
        out = self.record(data).stdout
        self.assertIn("already applied", out)
        self.assertEqual(len(self.topic()["attempts"]), 1)
        card = self.deck_json()["cards"][0]
        self.assertEqual(len(card["history"]), 1)
        self.srs("grade", card["id"], "5", "--kind", "review", "--op", "op-2", now="2026-09-27T10:00:00+02:00")
        out = self.srs("grade", card["id"], "5", "--kind", "review", "--op", "op-2", now="2026-09-27T10:00:00+02:00").stdout
        self.assertIn("already applied", out)
        self.assertEqual(len(self.deck_json()["cards"][0]["history"]), 2)

    def test_record_without_pending_is_refused(self):
        self.start_lesson()
        res = self.record({"result": "pass"}, expect=1)
        self.assertIn("no pending", res.stderr)

    def test_hints_are_recorded_as_assistance(self):
        self.start_lesson()
        self.state("ask", "n1")
        out = self.state("hint").stdout
        self.assertIn("What does the network forward?", out)
        self.state("hint")
        out = self.record({"result": "pass", "quality": 5}).stdout
        self.assertIn("help substep", out)
        self.assertIn("capped", out)
        self.assertEqual(self.node("n1")["readiness"], "provisional")

    def test_same_check_id_on_two_nodes_gives_two_cards_and_separate_rotation(self):
        self.start_lesson()
        self.state("prep-node", "n2", stdin=json.dumps(PREP_N1))  # same check ids q1/q2 on another node
        self.state("ask", "n1")
        self.record({"result": "pass", "quality": 5})
        out = self.state("ask", "n2").stdout
        self.assertIn("q1/v1", out, "rotation is per node: n2's q1 starts at v1")
        self.record({"result": "pass", "quality": 5})
        cards = self.deck_json()["cards"]
        self.assertEqual(len(cards), 2)
        self.assertEqual({c["check"] for c in cards}, {"n1/q1", "n2/q1"})
        self.assertTrue(all(len(c["history"]) == 1 for c in cards))

    def test_variants_rotate(self):
        self.start_lesson()
        self.state("ask", "n1")
        self.record({"result": "pass", "quality": 5})
        out = self.state("ask", "n1", "--check", "q1", "--kind", "review").stdout
        self.assertIn("q1/v2", out)


# --- 11-14. grading and scheduling ---------------------------------------------------------------

class TestSrsRules(Base):
    def make_card(self):
        return self.srs("add", "--topic", "t", "--type", "short", "--q", "q", "--a", "a", "--points", "p").stdout.strip()

    def card(self, cid):
        return next(c for c in self.deck_json()["cards"] if c["id"] == cid)

    def test_same_day_success_does_not_graduate_twice(self):
        cid = self.make_card()
        self.srs("grade", cid, "5", "--kind", "initial")
        c = self.card(cid)
        self.assertEqual((c["reps"], c["interval"], c["due"]), (1, 1, "2026-09-26"))
        self.srs("grade", cid, "5", "--kind", "practice")
        self.srs("grade", cid, "5", "--kind", "review")
        c = self.card(cid)
        self.assertEqual((c["reps"], c["interval"], c["due"]), (1, 1, "2026-09-26"), "no second graduation on the same day")
        self.assertEqual(len(c["history"]), 3)
        self.assertEqual(c["ease"], 2.6, "ease only changes when the schedule advances")

    def test_practice_does_not_skip_first_review(self):
        cid = self.make_card()
        self.srs("grade", cid, "5", "--kind", "practice")
        c = self.card(cid)
        self.assertEqual((c["reps"], c["due"]), (0, "2026-09-26"))

    def test_same_day_failure_is_not_ignored(self):
        cid = self.make_card()
        self.srs("grade", cid, "5", "--kind", "initial")
        self.srs("grade", cid, "1", "--kind", "practice")
        c = self.card(cid)
        self.assertEqual((c["reps"], c["lapses"], c["due"]), (0, 1, "2026-09-26"))

    def test_later_review_advances_failure_lapses(self):
        cid = self.make_card()
        self.srs("grade", cid, "4", "--kind", "initial")
        self.srs("grade", cid, "4", "--kind", "review", now="2026-09-26T09:00:00+02:00")
        c = self.card(cid)
        self.assertEqual((c["reps"], c["interval"], c["due"]), (2, 6, "2026-10-02"))
        self.srs("grade", cid, "2", "--kind", "review", now="2026-10-02T09:00:00+02:00")
        c = self.card(cid)
        self.assertEqual((c["reps"], c["interval"], c["due"], c["lapses"]), (0, 1, "2026-10-03", 1))

    def test_early_review_does_not_accelerate(self):
        cid = self.make_card()
        self.srs("grade", cid, "4", "--kind", "initial")
        self.srs("grade", cid, "5", "--kind", "review", now="2026-09-26T09:00:00+02:00")  # due 10-02
        out = self.srs("grade", cid, "5", "--kind", "review", now="2026-09-28T09:00:00+02:00").stdout
        self.assertIn("early review", out)
        c = self.card(cid)
        self.assertEqual((c["reps"], c["interval"], c["due"]), (2, 6, "2026-10-02"))

    def test_timezone_day_boundary(self):
        # 22:30 UTC on the 25th is already the 26th in Europe/Oslo
        cid = self.make_card()
        self.srs("grade", cid, "5", "--kind", "initial")
        self.srs("grade", cid, "5", "--kind", "review", now="2026-09-25T22:30:00Z")
        c = self.card(cid)
        self.assertEqual(c["history"][-1]["date"], "2026-09-26")
        self.assertEqual(c["reps"], 2)

    def test_missing_required_point_cannot_be_independent_recall(self):
        cid = self.make_card()
        out = self.srs("grade", cid, "4", "--missing-required").stdout
        self.assertIn("capped", out)
        c = self.card(cid)
        self.assertEqual(c["history"][-1]["q"], 2)
        self.assertEqual(c["reps"], 0)
        out = self.srs("grade", cid, "5", "--assisted").stdout
        self.assertIn("capped", out)
        self.assertEqual(self.card(cid)["history"][-1]["q"], 2)

    def test_record_with_missing_point_is_not_a_pass(self):
        self.start_lesson()
        self.state("ask", "n1")
        out = self.record({"result": "pass", "quality": 5, "required_missed": ["independent routing"]}).stdout
        self.assertIn("partial", out)
        a = self.topic()["attempts"][0]
        self.assertEqual((a["result"], a["quality"]), ("partial", 2))
        self.assertEqual(self.node("n1")["readiness"], "needs_repair")
        self.assertEqual(self.deck_json()["cards"][0]["history"][0]["q"], 2)

    def test_invalidate_key_preserves_history_and_stops_penalising(self):
        cid = self.make_card()
        self.srs("grade", cid, "1", "--kind", "initial")
        self.srs("grade", cid, "2", "--kind", "review", now="2026-09-26T09:00:00+02:00")
        before = self.card(cid)
        self.assertEqual((before["lapses"], before["ease"]), (2, 1.64))
        out = self.srs("invalidate-key", cid, "--reason", "not guaranteed by the spec",
                       stdin=json.dumps({"answer": "unspecified", "key_points": ["unspecified"]})).stdout
        self.assertIn("2 earlier attempt(s) kept", out)
        c = self.card(cid)
        self.assertEqual(len(c["history"]), 2)
        self.assertTrue(all(h["valid"] is False for h in c["history"]))
        self.assertEqual(c["key_history"][0]["answer"], "a")
        self.assertEqual((c["lapses"], c["ease"], c["reps"], c["rubric_version"]), (0, 2.5, 0, 2))
        self.assertTrue(c["needs_replacement_check"])
        self.assertEqual(c["answer"], "unspecified")
        # an amendment keeps evidence valid
        self.srs("amend-key", cid, "--reason", "clarified", stdin=json.dumps({"key_points": ["unspecified", "extra"]}))
        c = self.card(cid)
        self.assertEqual(c["rubric_version"], 3)
        self.assertEqual(len(c["key_history"]), 2)

    def test_due_selection_respects_budget_and_keeps_due_dates(self):
        ids = [self.make_card() for _ in range(6)]
        for i in ids:
            self.srs("grade", i, "1", "--kind", "initial")  # all due tomorrow
        out = self.srs("due", "--budget", "5", now="2026-09-30T09:00:00+02:00").stdout
        self.assertIn("6 card(s) due", out)
        self.assertIn("2 selected", out)
        self.assertIn("4 deferred, due dates unchanged", out)
        self.assertTrue(all(c["due"] == "2026-09-26" for c in self.deck_json()["cards"]))
        data = json.loads(self.srs("due", "--json", "--all", now="2026-09-30T09:00:00+02:00").stdout)
        self.assertEqual(len(data["selected"]), 6)

    def test_srs_grade_review_flags_node_retention(self):
        self.start_lesson()
        self.state("ask", "n1")
        self.record({"result": "pass", "quality": 5})
        cid = self.deck_json()["cards"][0]["id"]
        out = self.srs("grade", cid, "1", "--kind", "review", now="2026-09-27T10:00:00+02:00").stdout
        self.assertIn("n1 retention -> needs_review", out)
        n = self.node("n1")
        self.assertEqual((n["coverage"], n["readiness"], n["retention"]), ("covered", "ready", "needs_review"))
        self.srs("grade", cid, "5", "--kind", "review", now="2026-09-28T10:00:00+02:00")
        self.assertEqual(self.node("n1")["retention"], "demonstrated")

    def test_review_grade_updates_node_retention_not_readiness(self):
        self.start_lesson()
        self.state("ask", "n1")
        self.record({"result": "pass", "quality": 5})
        self.assertEqual(self.node("n1")["readiness"], "ready")
        self.state("ask", "n1", "--check", "q1", "--kind", "review", now="2026-09-27T10:00:00+02:00")
        self.record({"result": "fail"}, now="2026-09-27T10:00:00+02:00")
        n = self.node("n1")
        self.assertEqual((n["readiness"], n["retention"]), ("ready", "needs_review"))


# --- 15-16. durability ------------------------------------------------------------------------

class TestDurability(Base):
    def test_interrupted_multifile_operation_recovers(self):
        self.start_lesson()
        self.state("ask", "n1")
        # Simulate a crash after the journal and the state file were written but before the deck.
        state = self.state_json()
        deck = self.deck_json()
        state["topics"]["tcp-reliability"]["attempts"] = [{"id": "ax", "ts": self.now, "node": "n1", "check": "q1", "variant": "v1",
                                                            "kind": "initial", "result": "pass", "quality": 5}]
        state["topics"]["tcp-reliability"]["pending"]["stage"] = "completed"
        state["rev"] = state["rev"] + 1
        deck["cards"].append({"id": "cxx", "topic": "tcp-reliability", "node": "n1", "check": "q1", "type": "short", "question": "q",
                              "answer": "a", "key_points": ["k"], "options": [], "created": "2026-09-25", "due": "2026-09-26",
                              "interval": 1, "ease": 2.5, "reps": 1, "lapses": 0, "history": [], "suspended": False})
        deck["rev"] = deck["rev"] + 1
        journal = {"op": "op-crash", "ts": self.now, "writes": {str(self.root / "state" / "state.json"): state,
                                                              str(self.root / "state" / "deck.json"): deck}}
        (self.root / "state" / ".journal.json").write_text(json.dumps(journal), "utf-8")
        (self.root / "state" / "state.json").write_text(json.dumps(state), "utf-8")
        self.assertEqual(len(self.deck_json()["cards"]), 0)
        self.state("show")  # any load recovers
        self.assertFalse((self.root / "state" / ".journal.json").exists())
        self.assertEqual(len(self.deck_json()["cards"]), 1)
        self.assertEqual(self.topic()["pending"]["stage"], "completed")
        self.assertEqual(len(self.topic()["attempts"]), 1)
        log = (self.root / "state" / ".log" / "hooks.log").read_text()
        self.assertIn("recovered op op-crash", log)

    def test_hand_edit_between_read_and_write_is_a_conflict(self):
        self.start_lesson(prep=False, topic_prep=False)
        res = self.py("""
            import learnlib as L, json, pathlib
            with L.Store(write=True) as st:
                st.state["topics"]["tcp-reliability"]["goal"] = "mine"
                # someone edits the file underneath us, bypassing the lock (e.g. a hand edit)
                p = L.state_path(); raw = json.loads(p.read_text()); raw["rev"] += 1; raw["topics"]["tcp-reliability"]["goal"] = "theirs"
                p.write_text(json.dumps(raw))
                try:
                    st.commit()
                    print("NO CONFLICT")
                except L.ConflictError as exc:
                    print("CONFLICT", exc)
        """)
        self.assertIn("CONFLICT", res.stdout)
        self.assertEqual(self.topic()["goal"], "theirs")

    def test_concurrent_writers_are_serialised_and_nothing_is_lost(self):
        self.start_lesson(prep=False, topic_prep=False)
        holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
            import sys, time; sys.path.insert(0, {str(self.root / 'scripts')!r})
            import learnlib as L
            with L.Store(write=True) as st:
                st.state["topics"]["tcp-reliability"]["edge"].append("from A")
                time.sleep(2.5)
                st.commit()
            print("A done")
        """)], cwd=self.root, env=self.env(), stdout=subprocess.PIPE, text=True)
        time.sleep(0.5)
        t0 = time.monotonic()
        self.state("edge", "from B")
        waited = time.monotonic() - t0
        holder.wait(timeout=30)
        self.assertGreater(waited, 1.0, "B must wait for A's lock")
        self.assertEqual(self.topic()["edge"], ["from A", "from B"])

    def test_lock_timeout_reports_instead_of_writing(self):
        self.start_lesson(prep=False, topic_prep=False)
        lock = self.root / "state" / ".state.lock"
        lock.mkdir()
        (lock / "owner").write_text("1 now")
        res = self.py("""
            import learnlib as L
            try:
                with L.Store(write=True, lock_timeout=0.3) as st:
                    st.commit()
            except L.LockError as exc:
                print("LOCKED", exc)
        """)
        self.assertIn("LOCKED", res.stdout)

    def test_stale_lock_is_broken(self):
        self.start_lesson(prep=False, topic_prep=False)
        lock = self.root / "state" / ".state.lock"
        lock.mkdir()
        old = time.time() - 600
        os.utime(lock, (old, old))
        self.state("checkpoint", "after stale lock")
        self.assertIn("breaking stale lock", (self.root / "state" / ".log" / "hooks.log").read_text())

    def test_backup_and_restore_are_explicit_and_logged(self):
        self.start_lesson(prep=False, topic_prep=False)
        self.state("backup", "--label", "t")
        before = self.state_json()
        self.state("checkpoint", "later")
        listing = self.state("restore", "--list").stdout
        bak = [l.split()[0] for l in listing.splitlines() if "state.json" in l][0]
        self.state("restore", bak)
        self.assertEqual(self.state_json()["rev"], before["rev"])
        self.assertIn("restore:", (self.root / "state" / ".log" / "hooks.log").read_text())


# --- 17-18. exercises ---------------------------------------------------------------------------

class TestExercises(Base):
    def test_retry_file_is_what_gets_tested(self):
        self.cmd("exercise.py", "new", "--topic", "t", "--name", "ex", "--lang", "python")
        folder = self.root / "exercises" / "t" / "ex"
        (folder / "test_solution.py").write_text(textwrap.dedent("""
            import importlib, os, unittest
            solve = importlib.import_module(os.environ.get('SOLUTION_MODULE', 'solution')).solve
            class T(unittest.TestCase):
                def test_it(self): self.assertEqual(solve(2), 4)
            if __name__ == '__main__': unittest.main()
        """), "utf-8")
        (folder / "solution.py").write_text("def solve(x):\n    return 0\n", "utf-8")
        (folder / "retry-2026-10-01.py").write_text("def solve(x):\n    return x * 2\n", "utf-8")
        res = self.cmd("exercise.py", "check", "exercises/t/ex", expect=1)
        self.assertIn("FAIL", res.stdout)
        res = self.cmd("exercise.py", "check", "exercises/t/ex", "--file", "retry-2026-10-01.py")
        self.assertIn("PASS", res.stdout)
        self.assertIn("retry-2026-10-01.py", res.stdout)
        self.assertEqual((folder / "solution.py").read_text(), "def solve(x):\n    return 0\n", "the original is never overwritten")
        attempts = sorted(p.name for p in (folder / ".attempts").iterdir())
        self.assertEqual(len(attempts), 2)
        self.assertTrue(any("FAIL-solution.py" in a for a in attempts))
        self.assertTrue(any("PASS-retry-2026-10-01.py" in a for a in attempts))
        self.cmd("exercise.py", "check", "exercises/t/ex", "--file", "../outside.py", expect=1)

    @unittest.skipUnless(shutil.which("gcc"), "gcc not installed")
    def test_c_openmp_reference_passes_and_flawed_fail(self):
        self.cmd("exercise.py", "new", "--topic", "t", "--name", "sum", "--lang", "c")
        folder = self.root / "exercises" / "t" / "sum"
        res = self.cmd("exercise.py", "validate", "exercises/t/sum", timeout=300)
        self.assertIn("ok   reference.c: expected PASS, got PASS", res.stdout)
        self.assertIn("ok   flawed-offbyone.c: expected FAIL, got FAIL", res.stdout)
        self.assertIn("flawed-race.c", res.stdout)
        res = self.cmd("exercise.py", "check", "exercises/t/sum", expect=1, timeout=300)
        self.assertIn("FAIL", res.stdout)
        shutil.copy(folder / ".reference" / "reference.c", folder / "retry.c")
        res = self.cmd("exercise.py", "check", "exercises/t/sum", "--file", "retry.c", timeout=300)
        self.assertIn("PASS", res.stdout)
        self.assertIn("do not prove the absence of a data race", res.stdout)
        self.assertNotIn("reference", (folder / "solution.c").read_text())

    def test_env_reports_compiler(self):
        out = self.cmd("exercise.py", "env").stdout
        self.assertIn("C:", out)


# --- 19. isolation of the smoke test ------------------------------------------------------------

class TestSelftestIsolation(Base):
    def test_selftest_never_touches_absolute_configured_paths(self):
        # a "repo" whose config points at a sentinel vault with absolute paths
        repo = self.root / "repo"
        shutil.copytree(SCRIPTS, repo / "scripts", ignore=shutil.ignore_patterns("__pycache__", "tests"))
        sentinel = self.root / "real-vault"
        sentinel.mkdir()
        (repo / "learn.config.json").write_text(json.dumps({
            "notesDir": str(sentinel), "vizDir": str(sentinel / "viz"), "reviewsDir": str(sentinel / "reviews"),
            "exercisesDir": "exercises", "stateDir": "state", "timezone": "Europe/Oslo"}), "utf-8")
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        env.pop("LEARN_NOW", None)
        env["LEARN_SELFTEST_NO_SUITE"] = "1"
        res = subprocess.run(["bash", str(repo / "scripts" / "selftest.sh")], capture_output=True, text=True, env=env, timeout=600)
        self.assertEqual(res.returncode, 0, res.stdout[-3000:] + res.stderr[-2000:])
        self.assertIn("ALL OK", res.stdout)
        self.assertEqual(list(sentinel.rglob("*")), [], "the configured vault must stay untouched")
        self.assertFalse((repo / "state").exists(), "the repo's own state dir must stay untouched")


# --- hooks and snapshot ------------------------------------------------------------------------------

class TestLessonDetection(Base):
    def entry(self, command):
        return {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": command}}]}}

    def detect(self, command):
        res = self.py(f"""
            import learnlib as L
            print(L._entry_marks_lesson({self.entry(command)!r}))
        """)
        return res.stdout.strip() == "True"

    def test_real_invocations_mark_a_lesson(self):
        self.assertTrue(self.detect('python3 scripts/state.py resume parallel-programming-with-openmp'))
        self.assertTrue(self.detect('cd /x && python3 scripts/state.py start "OpenMP" --goal "exam"'))
        self.assertTrue(self.detect("python3 scripts/state.py record <<'EOF'\n{\"result\": \"pass\"}\nEOF"))

    def test_text_that_mentions_commands_does_not(self):
        self.assertFalse(self.detect("cat > .claude/skills/teach/SKILL.md <<'EOF'\nRun python3 scripts/state.py ask n7\nthen python3 scripts/state.py record\nEOF"))
        self.assertFalse(self.detect('git commit -m "teach loop: python3 scripts/state.py start, ask, record"'))
        self.assertFalse(self.detect("echo 'python3 scripts/state.py resume x'"))

    def idle(self, entries):
        path = self.root / "t.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in entries), "utf-8")
        res = self.py(f"""
            import learnlib as L
            print(L.prompts_since_lesson_activity({str(path)!r}))
        """)
        return res.stdout.strip()

    def test_lesson_goes_idle_after_other_work(self):
        def prompt(text):
            return {"type": "user", "message": {"role": "user", "content": text}}
        hook = {"type": "user", "isMeta": True, "message": {"role": "user", "content": "Stop hook feedback: ..."}}
        result = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}
        lesson = [prompt("continue"), self.entry("python3 scripts/state.py ask n7"), result, prompt("my answer"),
                  self.entry("python3 scripts/state.py record <<'EOF'\n{}\nEOF"), result]
        self.assertEqual(self.idle(lesson), "0")
        after = lesson + [prompt("stop"), self.entry('python3 scripts/state.py checkpoint "x"'), result, hook, prompt("commit that")]
        self.assertEqual(self.idle(after), "2", "checkpoint, tool results and hook feedback do not count")
        self.assertEqual(self.idle(after + [prompt("anything more?")]), "3")
        self.assertEqual(self.idle(after + [prompt("<command-name>/teach</command-name>")]), "0")
        self.assertEqual(self.idle([prompt("hello")]), "None")

    def test_stop_hook_silent_once_lesson_is_idle(self):
        self.start_lesson()
        (self.root / "state" / ".cursors").mkdir(parents=True, exist_ok=True)
        (self.root / "state" / ".cursors" / "s.lesson").write_text('{"offset": 0, "found": "2000-01-01T00:00:00+00:00"}', "utf-8")
        state = json.loads((self.root / "state" / "state.json").read_text("utf-8"))
        state["topics"][state["active_topic"]]["updated"] = "2000-01-01T00:00:00+00:00"
        (self.root / "state" / "state.json").write_text(json.dumps(state), "utf-8")
        path = self.root / "t.jsonl"
        base = [self.entry("python3 scripts/state.py ask n1"), {"type": "user", "message": {"content": "answer"}}]

        def stop(entries):
            path.write_text("".join(json.dumps(e) + "\n" for e in entries), "utf-8")
            return self.cmd("hook_stop_checkpoint.py", stdin=json.dumps({"session_id": "s", "transcript_path": str(path)})).stdout
        self.assertIn("block", stop(base))
        self.assertEqual(stop(base + [{"type": "user", "message": {"content": p}} for p in ("a", "b", "c")]).strip(), "")


class TestHooks(Base):
    def test_session_start_is_compact_and_shows_pending(self):
        self.start_lesson()
        self.state("ask", "n1")
        ctx = json.loads(self.cmd("hook_session_start.py", stdin='{"source":"startup"}').stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("PENDING", ctx)
        self.assertIn("awaiting", ctx)
        self.assertIn("Current chunk s1", ctx)
        self.assertLess(len(ctx.splitlines()), 20)
        self.assertNotIn("different packets, different paths", ctx, "keys never leak into the snapshot")

    def test_precompact_is_honest(self):
        self.start_lesson()
        out = json.loads(self.cmd("hook_precompact.py", stdin='{"trigger":"auto"}').stdout)["systemMessage"]
        self.assertIn("is saved in state/state.json", out)
        (self.root / "state" / "state.json").write_text("{", "utf-8")
        out = json.loads(self.cmd("hook_precompact.py", stdin='{"trigger":"auto"}').stdout)["systemMessage"]
        self.assertIn("could not be read", out)


# --- documents (learner-supplied PDFs) ---------------------------------------------------------

TINY_PDF = (b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n4 0 obj << /Type /Page /Parent 2 0 R >> endobj\n%%EOF\n")
DIGEST = {"summary": "Lecture notes on TCP.", "scope_role": "primary", "objectives": ["explain retransmission"],
          "sections": [{"id": "s1", "title": "Loss", "pages": "1-2", "depth": "explain", "nodes": ["n2"]}],
          "node_map": [{"node": "n2", "pages": "1-2", "focus": "why packets get lost", "depth": "explain"},
                       {"node": "n9", "label": "NEW: Congestion", "pages": "2", "focus": "cwnd"}],
          "conflicts": [{"claim": "routers retransmit", "pages": "2", "issue": "end hosts retransmit", "nodes": ["n2"]}]}


class TestDocuments(Base):
    def setUp(self):
        super().setUp()
        (self.root / "resources").mkdir()
        self.pdf = self.root / "resources" / "Course notes.pdf"
        self.pdf.write_bytes(TINY_PDF)
        self.start_lesson()

    def test_register_digest_and_show_by_node(self):
        out = self.state("source-add", "Course notes.pdf", "--role", "primary").stdout
        self.assertIn("'Course-notes'", out)
        self.assertIn("2 page(s)", out)
        src = next(x for x in self.topic()["prep"]["sources"] if x.get("kind") == "document")
        self.assertEqual(src["path"], "resources/Course notes.pdf")
        self.assertIn("not digested", self.state("prep-status").stdout)
        res = self.state("source-digest", "Course-notes", stdin=json.dumps(DIGEST))
        self.assertIn("n9", res.stderr)  # proposed node is reported, not rejected
        self.assertIn("digested, unchanged", self.state("source-show").stdout)
        by_node = self.state("source-show", "--node", "n2").stdout
        self.assertIn("pages 1-2", by_node)
        self.assertIn("routers retransmit", by_node)
        self.assertIn("No digested document maps to n1", self.state("source-show", "--node", "n1").stdout)
        self.state("source-digest", "Course-notes", stdin=json.dumps({"sections": []}), expect=1)

    def test_topic_reprep_keeps_documents_and_change_is_detected(self):
        self.state("source-add", "resources/Course notes.pdf", "--id", "notes")
        self.state("source-digest", "notes", stdin=json.dumps(DIGEST))
        self.state("prep-topic", stdin=json.dumps(TOPIC_PREP))
        ids = [x["id"] for x in self.topic()["prep"]["sources"]]
        self.assertIn("notes", ids)
        self.assertTrue(self.topic()["prep"]["sources"][-1]["digested"])
        self.pdf.write_bytes(TINY_PDF + b"% edited\n")
        self.assertIn("FILE CHANGED", self.state("prep-status").stdout)
        self.assertIn("WARNING", self.state("validate").stdout)  # a warning, not a failure

    def test_page_locators_count_as_known_sources(self):
        self.state("source-add", "resources/Course notes.pdf", "--id", "notes")
        prep = json.loads(json.dumps(PREP_N1))
        prep["claims"] = [{"id": "c1", "kind": "definition", "text": "t", "sources": ["notes:p2"]}]
        prep["source_refs"] = [{"source": "notes", "pages": "1-2", "note": "loss"}]
        res = self.state("prep-node", "n1", stdin=json.dumps(prep))
        self.assertNotIn("not in the topic registry", res.stderr)
        self.assertIn("Source pages: notes 1-2 (loss)", self.state("prep-show", "n1").stdout)

    def test_missing_file_is_refused(self):
        self.state("source-add", "nope.pdf", expect=1)


if __name__ == "__main__":
    unittest.main()
