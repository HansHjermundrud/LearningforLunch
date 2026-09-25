#!/usr/bin/env python3
"""Stop hook: enforce checkpoint discipline while a lesson is active.

If a topic is being probed, planned or taught and the state file has not
been updated for longer than checkpointMinutes (learn.config.json), the hook
blocks the stop once and asks the model to record where things stand. The
second stop passes (stop_hook_active), so this can never loop. In the normal
teaching loop `ask` and `record` update the state on every answer turn, so
this only fires during long stretches without a question.

Only a live lesson counts: once LESSON_IDLE_PROMPTS learner prompts have passed
without a lesson command (ask, record, prep-show, ...; checkpoint excluded), the
session has moved on to other work and the hook stays silent.

A review session (log target inside reviewsDir) is exempt: srs.py grade
saves each card as it goes. A corrupt state file is reported, not "fixed".
"""
from __future__ import annotations

import json
import sys

import learnlib as L


def in_review(state: dict) -> bool:
    target = state.get("log_target")
    if not target:
        return False
    try:
        L.resolve(target).relative_to(L.dir_path("reviewsDir"))
        return True
    except ValueError:
        return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        payload = {}
    if payload.get("stop_hook_active"):
        return
    try:
        lesson = L.lesson_session(payload.get("transcript_path"), payload.get("session_id", ""))
        if not lesson:
            return
        idle = L.prompts_since_lesson_activity(payload.get("transcript_path"), lesson.get("offset", 0))
        if idle is not None and idle > L.LESSON_IDLE_PROMPTS:
            return
        limit = float(L.config().get("checkpointMinutes", 12))
        began = L.parse_ts(lesson.get("found"))
        if began and (L.now() - began).total_seconds() / 60 < limit:
            return
        try:
            state = L.load_state()
        except L.LearnError as exc:
            L.hook_log(f"stop_checkpoint: state unreadable: {exc}")
            print(json.dumps({"systemMessage": f"Learning state could not be read ({exc}). Nothing was saved."}))
            return
        if in_review(state):
            return
        slug = state.get("active_topic")
        if not slug or slug not in state["topics"]:
            return
        topic = state["topics"][slug]
        if topic.get("status") not in ("probing", "planning", "teaching"):
            return
        updated = L.parse_ts(topic.get("updated"))
        if updated is None:
            return
        minutes = (L.now() - updated).total_seconds() / 60
        if minutes < limit:
            return
        reason = (
            f"Checkpoint overdue: {int(minutes)} min since the last state update for topic '{slug}'. "
            "Before ending the turn, record where the lesson stands with ONE command: "
            "`python3 scripts/state.py checkpoint \"<what was just taught or asked, and the result>\"` "
            "(or `record` if an answer is waiting to be graded, or `ask` if you just posed a question without it). "
            "Then end the turn. Do not repeat lesson content to the learner."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        L.hook_log(f"stop_checkpoint: blocked once ({int(minutes)} min) for {slug}")
    except Exception as exc:  # noqa: BLE001
        L.hook_log(f"stop_checkpoint error: {exc!r}")


if __name__ == "__main__":
    main()
