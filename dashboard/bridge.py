#!/usr/bin/env python3
"""Process-isolated adapter around the unmodified project modules.

Reads use Store(write=False), NOT load_state/load_deck, because the latter may
recover an interrupted journal and write to disk. Commands use original main().
"""
from __future__ import annotations
import contextlib
import io
import json
import os
import pathlib
import sys
import time

sys.dont_write_bytecode = True

def main():
    root = pathlib.Path(os.environ["CLAUDE_PROJECT_DIR"]).resolve()
    sys.path.insert(0, str(root / "scripts"))
    import learnlib as L
    import state as S
    import srs as R
    request = json.load(sys.stdin)
    kind = request.get("kind", "snapshot")
    if kind == "command":
        module = request["module"]
        if module not in ("state", "srs", "hook"):
            raise L.LearnError("Unsupported engine module")
        expected = request.get("expected_rev")
        if expected is not None:
            # The revision check is INSIDE the engine's write lock, not a
            # separate check-then-write. A stale live browser cannot overwrite
            # a question that Claude has just changed.
            original_enter = L.Store.__enter__
            def guarded_enter(self):
                original_enter(self)
                if self.write and int(self.state.get("rev", 0)) != int(expected):
                    self.__exit__(None, None, None)
                    raise L.ConflictError("The lesson changed. Refresh and review the current question before trying again.")
                return self
            L.Store.__enter__ = guarded_enter
        payload = request.get("stdin")
        payload = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else (payload or "")
        sys.stdin = io.StringIO(payload)
        if module == "hook":
            import hook_session_start as H
            H.main()
        elif module == "state":
            S.main(request["args"])
        else:
            R.main(request["args"])
        return
    # Avoid torn snapshots while another command is writing state + deck.
    for attempt in range(4):
        if L.journal_path().exists():
            time.sleep(0.04)
            continue
        before = [(p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in (L.state_path(), L.deck_path())]
        with L.Store(write=False) as st:
            state, deck = st.state, st.deck
        after = [(p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in (L.state_path(), L.deck_path())]
        if before == after and not L.journal_path().exists():
            break
    else:
        raise L.LearnError("An engine commit is in progress or awaiting journal recovery. The dashboard will retry; it will not repair project files.")
    L.validate_state(state)
    L.validate_deck(deck)
    topics = state.get("topics", {})
    slug = request.get("topic") or state.get("active_topic")
    if slug not in topics:
        slug = max(topics, key=lambda x: topics[x].get("updated", ""), default=None)
    topic = topics.get(slug)
    info = {"eligible": [], "blocked": [], "repairs": [], "recommended": None, "notes": {}}
    prep, pending, stage = {}, None, "idle"
    warnings = []
    if topic:
        e = S.eligible(topic)
        info = {"eligible": [n["id"] for n in e["eligible"]],
                "blocked": [{"id": n["id"], "reasons": reasons} for n, reasons in e["blocked"]],
                "repairs": [n["id"] for n in e["repairs"]],
                "recommended": e["recommended"]["id"] if e["recommended"] else None,
                "notes": e["notes"], "all_required_covered": e["all_required_covered"]}
        for n in topic.get("plan", {}).get("nodes", []):
            try:
                p = S.load_node_prep(slug, n["id"])
                if p:
                    prep[n["id"]] = p
            except (L.LearnError, OSError) as ex:
                warnings.append(str(ex))
        p = topic.get("pending")
        if p:
            pending = dict(p)
            try:
                check, v = S._resolve_variant(topic, slug, p)
                pending.update({"question": S._question_text(p["type"], v, p.get("params", {}).get("order")),
                                "key": v, "hints": check.get("hints", []), "review": check.get("review", False)})
            except (L.LearnError, OSError) as ex:
                pending["question"] = p.get("question_head", "Question unavailable")
                warnings.append(str(ex))
        if topic.get("status") in ("paused", "stopped"):
            stage = "paused"
        elif p and p.get("stage") == "awaiting":
            stage = "question"
        elif p and p.get("stage") == "recorded":
            stage = "assessment"
        elif topic.get("status") == "finished":
            stage = "complete"
        elif info["repairs"]:
            stage = "repair"
        elif topic.get("attempts"):
            stage = "evidence"
        elif topic.get("status") in ("probing", "planning") or not prep:
            stage = "prepare"
        else:
            stage = "teach"
    selected, deferred, minutes = R.select_due(deck["cards"], L.today(), float(L.config().get("reviewMinutes", 10)), None)
    # Pure scheduling helpers and the read-only Store; no hook invocation in a
    # live snapshot. Actual recovery is offered only in the disposable demo.
    summary = S.summary_text(state)
    data = {"date": L.today(), "now": L.ts(), "timezone": L.config().get("timezone") or "local",
            "root": str(root), "state_path": str(L.state_path()), "deck_path": str(L.deck_path()),
            "rev": state.get("rev", 0), "deck_rev": deck.get("rev", 0),
            "active_topic": state.get("active_topic"), "selected_topic": slug,
            "topics": [{"slug": k, "title": v["title"], "status": v["status"]} for k, v in topics.items()],
            "topic": topic, "pending": pending, "prep": prep, "eligibility": info, "stage": stage,
            "cards": deck["cards"], "due": {"selected": [c["id"] for c in selected],
            "deferred": [c["id"] for c in deferred], "minutes": minutes},
            "summary": summary, "warnings": warnings, "raw_state": state, "raw_deck": deck}
    print(json.dumps(data, ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
