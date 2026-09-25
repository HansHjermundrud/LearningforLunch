#!/usr/bin/env python3
"""Stop hook: enforce checkpoint discipline while a lesson is active.

If a topic is being probed, planned or taught and the state file has not
been updated for longer than checkpointMinutes (learn.config.json), the hook
blocks the stop once and asks the model to record a checkpoint first. The
second stop passes (stop_hook_active), so this can never loop.
"""
from __future__ import annotations

import json
import sys

import learnlib as L


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
            return  # only lesson/review sessions are held to the checkpoint rule
        limit = float(L.config().get("checkpointMinutes", 12))
        began = L.parse_ts(lesson.get("found"))
        if began and (L.now() - began).total_seconds() / 60 < limit:
            return  # a lesson that just (re)started is not overdue, however old the state is
        state = L.load_state()
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
            "Before ending the turn, record where the lesson stands: "
            "`python scripts/state.py checkpoint \"<one line: what was just taught or asked, and the learner's result>\"`, "
            "plus `node-done`, `node-shaky` or `next` if they apply. Then end the turn. "
            "Do not repeat lesson content to the learner."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        L.hook_log(f"stop_checkpoint: blocked once ({int(minutes)} min) for {slug}")
    except Exception as exc:  # noqa: BLE001
        L.hook_log(f"stop_checkpoint error: {exc!r}")


if __name__ == "__main__":
    main()
