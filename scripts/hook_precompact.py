#!/usr/bin/env python3
"""PreCompact hook: leave a trace and reassure the user.

Compaction itself is safe because the SessionStart hook re-injects the state
afterwards. This only logs the event and marks it in the lesson note so the
timeline in Obsidian shows where the teacher's context was summarised.
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
    try:
        state = L.load_state()
        target = state.get("log_target")
        if target and L.lesson_session(payload.get("transcript_path"), payload.get("session_id", "")):
            L.append_text(L.resolve(target), f"\n\n> [!note] Teacher context compacted ({trigger}) {L.fmt_local(L.ts())}; state restored from state/progress.md\n")
        L.hook_log(f"precompact: {trigger}")
    except Exception as exc:  # noqa: BLE001
        L.hook_log(f"precompact error: {exc!r}")
    print(json.dumps({"systemMessage": "Compacting: lesson state is safe in state/progress.md and will be re-injected."}))


if __name__ == "__main__":
    main()
