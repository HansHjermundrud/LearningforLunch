#!/usr/bin/env python3
"""SessionStart hook: inject the external memory into the fresh context.

Runs on startup, resume, /clear and after every compaction. Prints a JSON
object whose additionalContext tells the model today's date, the active
topic, the plan progress, the next step and how many review cards are due.
This is what stops the system from "losing itself": the chat context can be
thrown away at any time and rebuilt from here plus state/progress.md.
"""
from __future__ import annotations

import json
import subprocess
import sys

import learnlib as L


def deck_line() -> str:
    try:
        out = subprocess.run(
            [sys.executable, str(L.ROOT / "scripts" / "srs.py"), "stats", "--json"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
        stats = json.loads(out)
    except Exception:  # noqa: BLE001
        return "Reviews: deck unavailable."
    if stats["total"] == 0:
        return "Reviews: deck is empty."
    by_topic = ", ".join(f"{k} {v}" for k, v in sorted(stats["due_by_topic"].items()))
    line = f"Reviews: {stats['due_today']} card(s) due today" + (f" ({by_topic})" if by_topic else "")
    line += f"; {stats['due_next_7_days']} in the next 7 days; {stats['total']} total."
    if stats["due_today"]:
        line += " Offer /review before or after the lesson."
    return line


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        payload = {}
    source = payload.get("source", "startup")
    try:
        sys.path.insert(0, str(L.ROOT / "scripts"))
        import state as S  # noqa: WPS433

        state = L.load_state()
        summary = S.summary_text(state)
    except Exception as exc:  # noqa: BLE001
        L.hook_log(f"session_start error: {exc!r}")
        summary = "State unavailable (see state/.log/hooks.log)."
    header = f"[learning system · {source} · now {L.now().strftime('%A %Y-%m-%d %H:%M')} {L.config().get('timezone') or 'local time'}]"
    tail = (
        "Rules: use these dates for anything dated. If a topic is active and the learner wants to continue, "
        "resume at NEXT without re-teaching finished nodes; state/progress.md has the detail. "
        "Checkpoint with scripts/state.py after every node and phase change."
    )
    if source == "compact":
        tail = "Context was just compacted. " + tail
    context = "\n".join([header, summary, deck_line(), tail])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))


if __name__ == "__main__":
    main()
