#!/usr/bin/env python3
"""PreCompact hook: leave a trace and say honestly what is saved.

Compaction is safe when the state file is readable and no operation is half
written: the SessionStart hook re-injects the snapshot afterwards. This hook
checks both before claiming so, logs the event, and marks it in the lesson note.
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
    trigger = payload.get("trigger", "auto")
    message = "Compacting."
    try:
        state = L.load_state()
        slug = state.get("active_topic")
        topic = state["topics"].get(slug) if slug else None
        if topic:
            p = topic.get("pending")
            pend = f"; pending interaction {p['id']} ({p['stage']}) will be re-injected" if p and p.get("stage") != "completed" else ""
            message = (f"Compacting: lesson state for '{slug}' as of {L.fmt_local(topic.get('updated'))} is saved in state/state.json"
                       f"{pend}; NEXT and the snapshot are re-injected after compaction.")
        else:
            message = "Compacting: no active lesson; state/state.json is readable."
        target = state.get("log_target")
        if target and L.lesson_session(payload.get("transcript_path"), payload.get("session_id", "")):
            L.append_text(L.resolve(target), f"\n\n> [!note] Teacher context compacted ({trigger}) {L.fmt_local(L.ts())}; state restored from state/state.json\n")
        L.hook_log(f"precompact: {trigger}")
    except L.LearnError as exc:
        L.hook_log(f"precompact: {exc}")
        message = f"Compacting, but the learning state could not be read: {exc}"
    except Exception as exc:  # noqa: BLE001
        L.hook_log(f"precompact error: {exc!r}")
        message = "Compacting; the learning state could not be verified (see state/.log/hooks.log)."
    print(json.dumps({"systemMessage": message}))


if __name__ == "__main__":
    main()
