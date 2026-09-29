#!/usr/bin/env python3
"""Lesson state: the teacher's external memory.

The chat context is disposable. state.json, deck.json, the prepared material
under state/prep/ and the lesson note are what survive compaction, restarts and
new sessions. Every mutating command below goes through learnlib.Store (lock,
schema check, journal), rewrites state/progress.md and prints a short
confirmation. Read docs/SYSTEM.md for the data semantics.

Usage (run from the repo root):
  show [--full] · topics · validate · migrate · backup · restore --list | FILE
  start "Title" [--goal ...] [--slug s] · goal TEXT · edge TEXT · pause · resume SLUG · stop [--summary]
  plan-set < plan.json · plan-show [NODE] · plan-approve · node-add ID "label" [--depends a,b]
  prep-topic < topic.json · prep-node ID < node.json · prep-show ID [--keys] · prep-status
  source-add PATH [--id ID] [--role primary|supplementary] [--title T] [--pages 1-40] · source-digest ID < digest.json
  source-show [ID] [--node N]
  next-node · ask NODE [--check ID] [--variant ID] [--fresh] [--kind K] [--exit ID] [--adhoc < q.json] [--replace]
  pending [--keys] · answer TEXT|--file F · hint [--level nudge|substep|worked]
  record < result.json   (one call: attempt + readiness + card + next step)
  readiness ID VALUE --reason "..." · scope ID --optional|--required --reason "..."
  node-done ID "summary" [--check T] [--readiness R] · node-shaky ID "why" · node-edit ID [--label ..] [--depends a,b]
  correction "what" "why" [--node ID] [--card ID] [--sources a,b]
  next TEXT · checkpoint TEXT · history [--node ID] [--limit N] · finish [--summary] · log-target PATH|--clear
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys

import learnlib as L
import srs as R

MAX_LOG = 200
STATUSES = L.TOPIC_STATUS
MARK = {"ready": "✓", "provisional": "◐", "needs_repair": "~", "unknown": "?"}


# --- small helpers ----------------------------------------------------------------

def _topic(state: dict, slug: str | None = None) -> tuple[str, dict]:
    slug = slug or state.get("active_topic")
    if not slug or slug not in state["topics"]:
        raise L.LearnError('no active topic. Run: python3 scripts/state.py start "Title"')
    return slug, state["topics"][slug]


def _touch(topic: dict, event: str, text: str = "") -> None:
    topic["updated"] = L.ts()
    topic.setdefault("log", []).append({"ts": L.ts(), "event": event, "text": text})
    if len(topic["log"]) > MAX_LOG:
        topic["log"] = topic["log"][-MAX_LOG:]


def _nodes(topic: dict) -> list[dict]:
    return topic.get("plan", {}).get("nodes", [])


def _find_node(topic: dict, node_id: str) -> dict:
    for n in _nodes(topic):
        if n["id"] == node_id:
            return n
    raise L.LearnError(f"node '{node_id}' not in plan. Known: {[n['id'] for n in _nodes(topic)]}")


def sync_legacy(node: dict) -> None:
    """Keep the v1 `status` field as a mirror of coverage/readiness for old tooling."""
    if node.get("readiness") == "needs_repair":
        node["status"] = "shaky"
    elif node.get("coverage") == "covered":
        node["status"] = "done"
    else:
        node["status"] = "pending"


def _save(st: L.Store, message: str, op: str | None = None) -> None:
    for topic in st.state["topics"].values():
        for n in _nodes(topic):
            sync_legacy(n)
    st.commit(op_id=op)
    write_progress(st.state)
    print(message)


def _stdin_json() -> dict:
    raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise L.LearnError(f"expected JSON on stdin: {exc}")


# --- prepared material ---------------------------------------------------------------

def node_prep_path(slug: str, node_id: str):
    return L.prep_dir(slug) / f"{node_id}.json"


def load_node_prep(slug: str, node_id: str) -> dict | None:
    data = L.read_json(node_prep_path(slug, node_id), None)
    if data is None:
        return None
    L.validate_node_prep(data)
    return data


def all_checks(topic: dict, slug: str, node_id: str) -> list[dict]:
    prep = load_node_prep(slug, node_id)
    return list(prep.get("checks", [])) if prep else []


def exit_checks(topic: dict, criterion_id: str) -> tuple[dict, list[dict]]:
    for x in topic.get("prep", {}).get("exit_criteria", []):
        if x["id"] == criterion_id:
            return x, list(x.get("checks", []))
    raise L.LearnError(f"no exit criterion '{criterion_id}' in the topic prep")


# --- eligibility ----------------------------------------------------------------------

def eligible(topic: dict) -> dict:
    """Which nodes may be taught next, which are blocked and why, which need repair."""
    nodes = _nodes(topic)
    by_id = {n["id"]: n for n in nodes}
    out = {"eligible": [], "blocked": [], "repairs": [], "recommended": None, "all_required_covered": False, "notes": {}}
    for n in nodes:
        if n.get("readiness") == "needs_repair":
            out["repairs"].append(n)
    for n in nodes:
        if n.get("coverage") == "covered":
            continue
        blockers, notes = [], []
        for d in n.get("depends", []):
            dep = by_id.get(d)
            if dep is None:
                blockers.append(f"{d} missing")
            elif dep.get("coverage") != "covered":
                blockers.append(f"{d} not taught yet")
            elif dep.get("readiness") == "needs_repair":
                blockers.append(f"{d} needs repair")
            elif dep.get("readiness") == "unknown":
                notes.append(f"{d} covered without recorded evidence (check just in time if it matters)")
        if blockers:
            out["blocked"].append((n, blockers))
        else:
            out["eligible"].append(n)
            out["notes"][n["id"]] = notes
    required_pending = [n for n in nodes if n.get("required", True) and n.get("coverage") != "covered"]
    out["all_required_covered"] = not required_pending
    if out["eligible"]:
        out["recommended"] = out["eligible"][0]
    return out


def _exit_text(topic: dict) -> str:
    crit = topic.get("prep", {}).get("exit_criteria", [])
    if crit:
        missing = [x["id"] for x in crit if not _exit_passed(topic, x["id"])]
        if missing:
            return "All required nodes covered. Exit check: ask --exit " + ", ".join(missing) + "; then finish."
        return "Exit evidence complete: finish (python3 scripts/state.py finish --summary ...)."
    return "All required nodes covered, but no exit criteria are defined: prep-topic with exit_criteria, then the exit check, then finish."


def next_text(topic: dict, slug: str) -> str:
    info = eligible(topic)
    rec = info["recommended"]
    repairs = info["repairs"]
    if info["all_required_covered"] and not repairs:
        optional = [n["id"] for n in info["eligible"]]
        return _exit_text(topic) + (f" Optional nodes still open: {', '.join(optional)}." if optional else "")
    if rec is None and repairs:
        r = repairs[0]
        return f"Repair {r['id']} ({_head(r['label'])}) before building on it: {r.get('readiness_note') or r.get('summary', '')}"
    if rec is not None:
        prepared = load_node_prep(slug, rec["id"]) is not None
        text = f"Teach {rec['id']} · {_head(rec['label'])}"
        text += " (prepared; python3 scripts/state.py prep-show " + rec["id"] + ")" if prepared else " (NOT prepared: prep-node " + rec["id"] + " first)"
        if repairs:
            text += "; also owed: repair " + ", ".join(r["id"] for r in repairs)
        return text
    if info["all_required_covered"]:
        return _exit_text(topic) + (" Owed: repair " + ", ".join(r["id"] for r in repairs) if repairs else "")
    blocked = info["blocked"]
    if blocked:
        n, why = blocked[0]
        return f"No node is eligible: {n['id']} waits on " + "; ".join(why)
    return "Nothing pending."


def _exit_passed(topic: dict, criterion_id: str) -> bool:
    return any(a.get("exit") == criterion_id and a.get("result") == "pass" and a.get("independent", True)
               for a in topic.get("attempts", []))


# --- rendering ---------------------------------------------------------------

def _head(label: str) -> str:
    for sep in (":", ";", " (", " - "):
        idx = label.find(sep)
        if idx >= 12:
            return label[:idx].strip()
    return label.strip()


def _node_line(node: dict) -> str:
    cov = node.get("coverage", "pending")
    rd = node.get("readiness", "unknown")
    mark = MARK.get(rd, "?") if cov == "covered" else "·"
    check = node.get("check") or ""
    check = f" [{check}]" if check and check != "none" else ""
    opt = "" if node.get("required", True) else " (optional)"
    state = f" · {rd}" if cov == "covered" else ""
    ret = f" · {node['retention']}" if node.get("retention") not in (None, "unassessed") else ""
    summary = f" — {node['summary']}" if node.get("summary") else ""
    return f"{mark} {node['id']} {node.get('label', '')}{check}{opt}{state}{ret}{summary}"


def _short(label: str, width: int = 30, max_lines: int = 3) -> str:
    label = label.replace('"', "'")
    words = label.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    return "<br>".join(lines)


def plan_mermaid(topic: dict, focus: str | None = None) -> str:
    nodes = _nodes(topic)
    if not nodes:
        return topic.get("plan", {}).get("mermaid", "")
    ids = {n["id"] for n in nodes}
    keep = ids
    if focus:
        keep = {focus}
        keep |= {d for n in nodes if n["id"] == focus for d in n.get("depends", [])}
        keep |= {n["id"] for n in nodes if focus in n.get("depends", [])}
    shown = [n for n in nodes if n["id"] in keep]
    lines = ["graph TD"]
    for n in shown:
        lines.append(f'  {n["id"]}["{n["id"]} · {_short(n.get("label", ""))}"]')
    for n in shown:
        for d in n.get("depends", []):
            if d in keep and d in ids:
                lines.append(f"  {d} --> {n['id']}")
    done = [n["id"] for n in shown if n.get("coverage") == "covered" and n.get("readiness") != "needs_repair"]
    shaky = [n["id"] for n in shown if n.get("readiness") == "needs_repair"]
    lines.append("  classDef done fill:#d9efe9,stroke:#0e7c74,color:#1b2430")
    lines.append("  classDef shaky fill:#fbe9d7,stroke:#b9600a,color:#1b2430")
    lines.append("  classDef current fill:#fff4c2,stroke:#b8860b,stroke-width:2px,color:#1b2430")
    if done:
        lines.append("  class " + ",".join(done) + " done")
    if shaky:
        lines.append("  class " + ",".join(shaky) + " shaky")
    if focus and focus in ids:
        lines.append(f"  class {focus} current")
    return "\n".join(lines)


def node_context(topic: dict, node_id: str) -> str:
    nodes = {n["id"]: n for n in _nodes(topic)}
    node = nodes.get(node_id)
    if not node:
        return f"Node {node_id} is not in the plan."
    name = lambda i: f"{i} · {_head(nodes[i]['label'])}" if i in nodes else i  # noqa: E731
    builds_on = ", ".join(name(d) for d in node.get("depends", [])) or "nothing (a foundation)"
    leads_to = ", ".join(name(n["id"]) for n in nodes.values() if node_id in n.get("depends", [])) or "the goal directly"
    return f"**{node_id} · {node['label']}**\nBuilds on: {builds_on}.\nLeads to: {leads_to}."


def pending_line(topic: dict) -> str:
    p = topic.get("pending")
    if not p or p.get("stage") == "completed":
        return ""
    q = (p.get("question_head") or "").strip().splitlines()[0] if p.get("question_head") else ""
    q = (q[:90] + "…") if len(q) > 90 else q
    stage = {"awaiting": "awaiting the learner's answer", "recorded": "answer recorded, NOT yet graded (run record)"}[p["stage"]]
    where = f"{p['node']} {p['check']}/{p['variant']}" if not p.get("exit") else f"exit {p['exit']} {p['check']}/{p['variant']}"
    hints = f" · hints given: {len(p.get('assistance', []))}" if p.get("assistance") else ""
    return f"PENDING {p['id']} · {p['type']} · {where} · {stage} (asked {L.fmt_local(p.get('asked_at'), '%H:%M')}){hints}" + (f'\n  Q: "{q}"' if q else "")


def summary_text(state: dict, full: bool = False) -> str:
    """Compact snapshot for hooks and /status (about 12 lines); --full lists every node."""
    lines = []
    slug = state.get("active_topic")
    if slug and slug in state["topics"]:
        topic = state["topics"][slug]
        nodes = _nodes(topic)
        covered = [n for n in nodes if n.get("coverage") == "covered"]
        req = [n for n in nodes if n.get("required", True)]
        by_rd = {k: sum(1 for n in covered if n.get("readiness") == k) for k in L.READINESS}
        lines.append(
            f"Active topic: {topic['title']} ({slug}) · status: {topic['status']} · "
            f"started {topic['started']} · last update {L.fmt_local(topic['updated'])}"
        )
        if topic.get("note"):
            lines.append(f"Lesson note: {L.rel(topic['note'])}")
        if topic.get("goal"):
            lines.append(f"Goal: {topic['goal']}")
        if topic.get("edge"):
            lines.append("Edge: " + " | ".join(topic["edge"][-3:]))
        plan = topic.get("plan") or {}
        if nodes:
            approved = "approved" if plan.get("approved") else "NOT yet approved by the learner"
            lines.append(
                f"Plan ({approved}): {len(covered)}/{len(nodes)} covered ({len(req)} required) · "
                f"ready {by_rd['ready']} · provisional {by_rd['provisional']} · needs repair {by_rd['needs_repair']} · "
                f"unverified legacy {by_rd['unknown']} · pending {len(nodes) - len(covered)}"
            )
            chunk = current_chunk(topic)
            if chunk:
                prepared = [i for i in chunk["nodes"] if load_node_prep(slug, i) is not None]
                lines.append(f"Current chunk {chunk['id']} \"{chunk.get('label', '')}\": " + ", ".join(chunk["nodes"])
                             + (f" · prepared: {', '.join(prepared)}" if prepared else " · nothing prepared yet"))
            if full:
                for node in nodes:
                    lines.append("  " + _node_line(node))
        elif topic["status"] in ("planning", "teaching"):
            lines.append("Plan: none recorded yet (run plan-set).")
        pl = pending_line(topic)
        if pl:
            lines.append(pl)
        if topic.get("next"):
            lines.append(f"NEXT: {topic['next']}")
        log = topic.get("log", [])
        if log:
            last = log[-1]
            lines.append(f"Last checkpoint: {L.fmt_local(last['ts'])} · {last['event']}: {last['text'][:160]}")
    else:
        lines.append("No active topic.")
        recent = sorted(state["topics"].values(), key=lambda t: t.get("updated", ""), reverse=True)[:5]
        if recent:
            lines.append("Recent topics: " + "; ".join(f"{t['title']} ({t['status']}, {t['started']})" for t in recent))
    if state.get("log_target"):
        lines.append(f"Session log target: {L.rel(state['log_target'])}")
    return "\n".join(lines)


def current_chunk(topic: dict) -> dict | None:
    """The first chunk that still has an uncovered node."""
    by_id = {n["id"]: n for n in _nodes(topic)}
    for ch in topic.get("prep", {}).get("chunks", []):
        if any(by_id.get(i, {}).get("coverage") != "covered" for i in ch.get("nodes", [])):
            return ch
    return None


def write_progress(state: dict) -> None:
    out = ["# Learning progress", f"_Updated {L.fmt_local(L.ts())}_", ""]
    slug = state.get("active_topic")
    if slug and slug in state["topics"]:
        topic = state["topics"][slug]
        out.append(f"## Active: {topic['title']} (`{slug}`) · {topic['status']}")
        out.append(f"- Started: {topic['started']} · Updated: {L.fmt_local(topic['updated'])}")
        if topic.get("note"):
            out.append(f"- Note: `{L.rel(topic['note'])}`")
        if topic.get("goal"):
            out.append(f"- Goal: {topic['goal']}")
        if topic.get("prep", {}).get("capability"):
            out.append(f"- Target capability: {topic['prep']['capability']}")
        if topic.get("edge"):
            out.append("- Edge findings:")
            out.extend(f"  - {e}" for e in topic["edge"])
        pl = pending_line(topic)
        if pl:
            out.append(f"- **Pending interaction:** {pl.splitlines()[0]}")
        if topic.get("next"):
            out.append(f"- **Next:** {topic['next']}")
        nodes = _nodes(topic)
        if nodes:
            out.append("")
            out.append(f"### Plan ({'approved' if topic.get('plan', {}).get('approved') else 'not approved'})")
            out.append("| id | node | depends on | required | coverage | readiness | retention | check | summary |")
            out.append("|---|---|---|---|---|---|---|---|---|")
            for n in nodes:
                out.append(
                    f"| {n['id']} | {n.get('label','')} | {', '.join(n.get('depends', []))} | {'yes' if n.get('required', True) else 'no'} | "
                    f"{n.get('coverage','pending')} | {n.get('readiness','unknown')} | {n.get('retention','unassessed')} | "
                    f"{n.get('check','') or ''} | {n.get('summary','') or ''} |"
                )
        mermaid = plan_mermaid(topic)
        if mermaid:
            out.append("")
            out.append("```mermaid")
            out.append(mermaid.strip())
            out.append("```")
        attempts = topic.get("attempts", [])
        if attempts:
            out.append("")
            out.append("### Recent attempts")
            for a in attempts[-10:]:
                out.append(f"- {L.fmt_local(a['ts'])} · {a['node']} {a.get('check','')}/{a.get('variant','')} · {a['kind']} · "
                           f"{a['result']} q={a.get('quality')} · help: {a.get('assistance','none')}"
                           + (f" · misconception: {a['misconception']}" if a.get("misconception") else ""))
        corrections = topic.get("corrections", [])
        if corrections:
            out.append("")
            out.append("### Material corrections")
            for c in corrections[-10:]:
                out.append(f"- {c.get('date')} · {c.get('what')} · {c.get('why')}")
        log = topic.get("log", [])
        if log:
            out.append("")
            out.append("### Recent log")
            for entry in log[-12:]:
                out.append(f"- {L.fmt_local(entry['ts'])} · {entry['event']} · {entry['text']}")
        out.append("")
    others = [t for s, t in state["topics"].items() if s != slug]
    if others:
        out.append("## All topics")
        out.append("| slug | title | status | started | finished | nodes covered |")
        out.append("|---|---|---|---|---|---|")
        for s, t in sorted(state["topics"].items(), key=lambda kv: kv[1].get("updated", ""), reverse=True):
            nodes = _nodes(t)
            done = sum(1 for n in nodes if n.get("coverage") == "covered")
            out.append(f"| {s} | {t['title']} | {t['status']} | {t['started']} | {t.get('finished') or ''} | {done}/{len(nodes)} |")
    (L.dir_path("stateDir", create=True) / "progress.md").write_text("\n".join(out) + "\n", "utf-8")


# --- read-only commands ----------------------------------------------------------------

def cmd_show(args):
    print(summary_text(L.load_state(), full=args.full))


def cmd_topics(args):
    state = L.load_state()
    if not state["topics"]:
        print("No topics yet.")
        return
    for slug, t in sorted(state["topics"].items(), key=lambda kv: kv[1].get("updated", ""), reverse=True):
        active = "*" if slug == state.get("active_topic") else " "
        nodes = _nodes(t)
        done = sum(1 for n in nodes if n.get("coverage") == "covered")
        print(f"{active} {slug:28} {t['status']:9} {t['started']}  {done}/{len(nodes)} nodes  {t['title']}")


def cmd_validate(args):
    problems = []
    try:
        state = L.load_state()
        L.validate_state(state)
    except L.LearnError as exc:
        problems.append(f"state: {exc}")
        state = {"topics": {}}
    try:
        L.validate_deck(L.load_deck())
    except L.LearnError as exc:
        problems.append(f"deck: {exc}")
    for slug in state.get("topics", {}):
        folder = L.prep_dir(slug)
        if folder.exists():
            for f in sorted(folder.glob("*.json")):
                try:
                    L.validate_node_prep(L.read_json(f, {}))
                except L.LearnError as exc:
                    problems.append(f"prep {L.rel(f)}: {exc}")
            for f in sorted((folder / "sources").glob("*.json")):
                try:
                    L.validate_source_digest(L.read_json(f, {}))
                except L.LearnError as exc:
                    problems.append(f"digest {L.rel(f)}: {exc}")
        for src in _documents(state["topics"][slug]):
            status = _doc_status(slug, src)
            if status != "digested, unchanged":
                print(f"WARNING: {slug} document {src['id']}: {status}")
    if problems:
        for p in problems:
            print("PROBLEM: " + p)
        sys.exit(1)
    print("state, deck and prepared material validate OK")


def cmd_history(args):
    state = L.load_state()
    slug, topic = _topic(state)
    attempts = [a for a in topic.get("attempts", []) if not args.node or a.get("node") == args.node]
    for a in attempts[-args.limit:]:
        print(f"{a['id']} {L.fmt_local(a['ts'])} {a['node']} {a.get('check','')}/{a.get('variant','')} v{a.get('rubric_version',1)} "
              f"{a['kind']} {a['result']} q={a.get('quality')} help={a.get('assistance','none')}"
              + (f" misconception={a['misconception']}" if a.get("misconception") else "")
              + (f" card={a['card']}" if a.get("card") else "")
              + (f"\n    {a['response'][:200]}" if a.get("response") else ""))
    if not attempts:
        print("No attempts recorded.")


# --- maintenance ---------------------------------------------------------------------------

def cmd_migrate(args):
    with L.Store(write=True) as st:
        if not st.migration_steps:
            print(f"state v{st.state['version']} and deck v{st.deck['version']} are current; nothing to do")
            return
        for s in st.migration_steps:
            print("migrate: " + s)
        _save(st, "migrated; byte-for-byte backups of the previous files are in " + L.rel(L.backups_dir()))


def cmd_backup(args):
    made = [L.backup_file(p, label=args.label or "manual") for p in (L.state_path(), L.deck_path())]
    for m in made:
        if m:
            print("backup: " + L.rel(m))


def cmd_restore(args):
    folder = L.backups_dir()
    if args.list or not args.file:
        files = sorted(folder.glob("*.bak"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
        if not files:
            print("No backups yet (they are made before migrations and by: python3 scripts/state.py backup).")
        for f in files:
            print(f"{L.rel(f)}  {f.stat().st_size} bytes")
        if not args.file:
            return
    src = L.resolve(args.file)
    if not src.exists():
        raise L.LearnError(f"no such backup: {src}")
    name = src.name.split(".")[0]
    target = {"state": L.state_path(), "deck": L.deck_path()}.get(name)
    if target is None:
        raise L.LearnError("backup file name must start with state.json or deck.json")
    try:
        json.loads(src.read_text("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise L.LearnError(f"backup is not valid JSON: {exc}")
    with L.Lock():
        kept = L.backup_file(target, label="before-restore")
        import shutil
        shutil.copy2(src, target)
    L.hook_log(f"restore: {L.rel(src)} -> {L.rel(target)} (previous kept as {L.rel(kept) if kept else 'none'})")
    print(f"restored {L.rel(target)} from {L.rel(src)}; the replaced file is kept as {L.rel(kept) if kept else 'none'}")


# --- topic lifecycle --------------------------------------------------------------------

def _new_note(title: str, slug: str) -> str:
    notes = L.dir_path("notesDir", create=True)
    base = f"{L.today()} {title}".replace("/", "-").replace(":", "-")
    path = notes / f"{base}.md"
    n = 2
    while path.exists():
        path = notes / f"{base} ({n}).md"
        n += 1
    header = (
        "---\n"
        f"title: \"{title}\"\n"
        f"date: {L.today()}\n"
        f"topic: {slug}\n"
        "status: active\n"
        "tags: [learning]\n"
        "---\n"
        f"# {title}\n\n"
        f"> [!info] Lesson started {L.fmt_local(L.ts())}\n"
    )
    path.write_text(header, "utf-8")
    return str(path)


def cmd_start(args):
    with L.Store(write=True) as st:
        state = st.state
        slug = args.slug or L.slugify(args.title)
        if slug in state["topics"] and state["topics"][slug]["status"] != "finished":
            state["active_topic"] = slug
            topic = state["topics"][slug]
            state["log_target"] = topic.get("note")
            _touch(topic, "resume", "resumed via start")
            _save(st, f"Topic '{slug}' already exists; made it active (status {topic['status']}).")
            return
        if slug in state["topics"]:
            slug = f"{slug}-{L.today()}"
        previous = state.get("active_topic")
        if previous and previous in state["topics"] and state["topics"][previous]["status"] in ("probing", "planning", "teaching"):
            state["topics"][previous]["status"] = "paused"
            _touch(state["topics"][previous], "pause", f"parked when '{slug}' started; resume with: python3 scripts/state.py resume {previous}")
        note = _new_note(args.title, slug)
        topic = {
            "title": args.title, "started": L.today(), "updated": L.ts(), "finished": None, "status": "probing",
            "goal": args.goal or "", "note": note, "edge": [],
            "plan": {"approved": False, "mermaid": "", "nodes": []}, "prep": {}, "attempts": [], "pending": None,
            "corrections": [],
            "next": "Probe briefly (3-5 informative questions), pin the goal if unclear, then prepare and present a plan.",
            "log": [],
        }
        _touch(topic, "start", f"topic created, note {L.rel(note)}")
        state["topics"][slug] = topic
        state["active_topic"] = slug
        state["log_target"] = note
        _save(st, f"Started topic '{slug}'. Note: {L.rel(note)}. Status: probing.")


def cmd_goal(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        topic["goal"] = args.text
        _touch(topic, "goal", args.text)
        _save(st, f"Goal recorded for '{slug}'.")


def cmd_edge(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        topic.setdefault("edge", []).append(args.text)
        _touch(topic, "edge", args.text)
        _save(st, f"Edge finding recorded ({len(topic['edge'])} total).")


def cmd_pause(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        topic["status"] = "paused"
        _touch(topic, "pause", "paused by learner")
        st.state["active_topic"] = None
        st.state["log_target"] = None
        _save(st, f"Topic '{slug}' paused. Resume with: python3 scripts/state.py resume {slug}")


def cmd_resume(args):
    with L.Store(write=True) as st:
        state = st.state
        if args.slug not in state["topics"]:
            raise L.LearnError(f"unknown topic '{args.slug}'")
        topic = state["topics"][args.slug]
        if topic["status"] == "finished":
            raise L.LearnError("topic is finished; start a new topic or review it with /review")
        if topic["status"] in ("paused", "stopped"):
            topic["status"] = "teaching" if topic.get("plan", {}).get("approved") else ("planning" if _nodes(topic) else "probing")
        state["active_topic"] = args.slug
        state["log_target"] = topic.get("note")
        _touch(topic, "resume", "resumed")
        if topic.get("note"):
            L.append_text(topic["note"], f"\n\n> [!info] Session resumed {L.fmt_local(L.ts())}\n")
        pl = pending_line(topic)
        _save(st, f"Resumed '{args.slug}' (status {topic['status']}).\n" + (pl + "\n" if pl else "") + f"NEXT: {topic.get('next','')}")


def cmd_stop(args):
    """End work on the topic without recording completion or mastery."""
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        topic["status"] = "stopped"
        if args.summary:
            topic["summary"] = args.summary
        topic["next"] = "Stopped by the learner; resume with: python3 scripts/state.py resume " + slug
        _touch(topic, "stop", args.summary or "stopped without completion")
        st.state["active_topic"] = None
        st.state["log_target"] = None
        _save(st, f"Topic '{slug}' stopped (no completion recorded). Reviews for its cards continue.")


def cmd_finish(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        problems = []
        for n in _nodes(topic):
            if not n.get("required", True):
                continue
            if n.get("coverage") != "covered":
                problems.append(f"{n['id']} not taught")
            elif n.get("readiness") not in ("ready", "provisional"):
                problems.append(f"{n['id']} readiness is {n.get('readiness')}")
        crit = topic.get("prep", {}).get("exit_criteria", [])
        if not crit:
            problems.append("no exit criteria defined (prep-topic with exit_criteria); the goal needs exit evidence")
        for x in crit:
            if not _exit_passed(topic, x["id"]):
                problems.append(f"exit criterion {x['id']} has no independent passing attempt")
        p = topic.get("pending")
        if p and p.get("stage") != "completed":
            problems.append(f"pending interaction {p['id']} is {p['stage']}")
        if problems:
            raise L.LearnError("cannot finish:\n  - " + "\n  - ".join(problems)
                               + "\nUse `stop` to end without recording completion, or `scope ID --optional` to reduce the agreed scope.")
        topic["status"] = "finished"
        topic["finished"] = L.today()
        topic["next"] = "Finished. Reviews are scheduled in the deck."
        if args.summary:
            topic["summary"] = args.summary
        _touch(topic, "finish", args.summary or "topic finished")
        if topic.get("note"):
            L.append_text(topic["note"], f"\n\n> [!success] Topic finished {L.fmt_local(L.ts())}\n" + (f"\n{args.summary}\n" if args.summary else ""))
        st.state["active_topic"] = None
        st.state["log_target"] = None
        _save(st, f"Topic '{slug}' finished on {topic['finished']}.")


def cmd_log_target(args):
    with L.Store(write=True) as st:
        if args.clear:
            st.state["log_target"] = None
            _save(st, "Session log target cleared.")
            return
        if not args.path:
            raise L.LearnError("give a path or --clear")
        path = L.resolve(args.path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"---\ndate: {L.today()}\ntags: [learning]\n---\n", "utf-8")
        st.state["log_target"] = str(path)
        _save(st, f"Session log target: {L.rel(path)}")


# --- plan ------------------------------------------------------------------------------------

def _node_from_input(n: dict, existing: dict | None) -> dict:
    node = dict(existing) if existing else {}
    node.update({"id": str(n["id"]), "label": str(n["label"]), "depends": [str(d) for d in n.get("depends", [])]})
    node["why"] = n.get("why", node.get("why", ""))
    node["required"] = bool(n.get("required", node.get("required", True)))
    node.setdefault("check", n.get("check", ""))
    node.setdefault("summary", n.get("summary", ""))
    legacy = n.get("status")
    if legacy and legacy not in L.LEGACY_STATUS:
        raise L.ValidationError(f"node {node['id']}: status must be one of {L.LEGACY_STATUS}")
    if "coverage" in n or "readiness" in n:
        node["coverage"] = n.get("coverage", node.get("coverage", "pending"))
        node["readiness"] = n.get("readiness", node.get("readiness", "unknown"))
    elif legacy and not existing:
        node["coverage"] = "covered" if legacy in ("done", "shaky") else "pending"
        node["readiness"] = {"done": "unknown", "shaky": "needs_repair"}.get(legacy, "unknown")
    node.setdefault("coverage", "pending")
    node.setdefault("readiness", "unknown")
    node.setdefault("retention", "unassessed")
    node.setdefault("prepared", False)
    sync_legacy(node)
    return node


def cmd_plan_set(args):
    data = _stdin_json()
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        existing = {n["id"]: n for n in _nodes(topic)}
        nodes = [_node_from_input(n, existing.get(str(n.get("id")))) for n in data.get("nodes", [])]
        L.validate_plan(nodes)
        topic["plan"] = {"approved": False, "mermaid": data.get("mermaid", ""), "nodes": nodes}
        topic["status"] = "planning"
        topic["next"] = "Present the plan (a few sentences + the generated map) and get one go-ahead; then plan-approve."
        _touch(topic, "plan-set", f"{len(nodes)} nodes")
        _save(st, f"Plan recorded with {len(nodes)} nodes (not yet approved).")


def cmd_plan_show(args):
    state = L.load_state()
    slug, topic = _topic(state)
    nodes = _nodes(topic)
    if not nodes:
        print("No plan recorded yet.")
        return
    if args.node:
        print(node_context(topic, args.node))
        print()
    print("```mermaid")
    print(plan_mermaid(topic, args.node))
    print("```")
    if not args.node:
        done = sum(1 for n in nodes if n.get("coverage") == "covered")
        print(f"\n{done}/{len(nodes)} nodes covered. Green = covered, orange = needs repair, yellow = current. Refer to nodes as `id · label`.")


def cmd_plan_approve(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        L.validate_plan(_nodes(topic))
        topic.setdefault("plan", {})["approved"] = True
        topic["status"] = "teaching"
        topic["next"] = next_text(topic, slug)
        _touch(topic, "plan-approve", "learner approved the plan")
        _save(st, f"Plan approved. Status: teaching. NEXT: {topic['next']}")


def cmd_node_add(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        nodes = topic.setdefault("plan", {"approved": False, "mermaid": "", "nodes": []}).setdefault("nodes", [])
        if any(n["id"] == args.id for n in nodes):
            raise L.LearnError(f"node '{args.id}' already exists")
        depends = [d.strip() for d in (args.depends or "").split(",") if d.strip()]
        candidate = nodes + [_node_from_input({"id": args.id, "label": args.label, "depends": depends, "required": not args.optional}, None)]
        L.validate_plan(candidate)
        nodes.append(candidate[-1])
        _touch(topic, "node-add", f"{args.id} {args.label}")
        _save(st, f"Node '{args.id}' added ({len(nodes)} nodes).")


def cmd_next_node(args):
    state = L.load_state()
    slug, topic = _topic(state)
    info = eligible(topic)
    if info["repairs"]:
        print("Needs repair: " + "; ".join(f"{n['id']} ({n.get('readiness_note') or n.get('summary','')})" for n in info["repairs"]))
    if info["eligible"]:
        print("Eligible now: " + ", ".join(n["id"] for n in info["eligible"]))
        for n in info["eligible"]:
            for note in info["notes"].get(n["id"], []):
                print(f"  note for {n['id']}: {note}")
    for n, why in info["blocked"]:
        print(f"Blocked: {n['id']} waits on " + "; ".join(why))
    print("Recommended: " + next_text(topic, slug))


def _has_independent_pass(topic: dict, node_id: str) -> bool:
    return any(a.get("node") == node_id and a.get("result") == "pass" and a.get("independent", False)
               and a.get("kind") in ("initial", "exit", "review") for a in topic.get("attempts", []))


def cmd_node_done(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        node = _find_node(topic, args.id)
        readiness = args.readiness or "provisional"
        if readiness == "ready" and not _has_independent_pass(topic, args.id):
            raise L.LearnError(f"no independent passing attempt is recorded for {args.id}; record one with `ask`/`record`, "
                               f"or use --readiness provisional (default) with the summary as the reason")
        node.update({"coverage": "covered", "readiness": readiness, "summary": args.summary,
                     "check": args.check or node.get("check") or "", "covered_at": L.ts(), "done_at": L.ts(),
                     "readiness_note": args.summary if readiness != "ready" else ""})
        topic["next"] = next_text(topic, slug)
        _touch(topic, "node-done", f"{args.id} ({readiness}): {args.summary}")
        _save(st, f"Node '{args.id}' covered, readiness {readiness}. NEXT: {topic['next']}")


def cmd_node_shaky(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        node = _find_node(topic, args.id)
        node.update({"coverage": "covered", "readiness": "needs_repair", "readiness_note": args.why, "summary": args.why})
        node.setdefault("covered_at", L.ts())
        topic["next"] = next_text(topic, slug)
        _touch(topic, "node-shaky", f"{args.id}: {args.why}")
        _save(st, f"Node '{args.id}' needs repair. NEXT: {topic['next']}")


def cmd_readiness(args):
    if args.value not in L.READINESS:
        raise L.LearnError(f"readiness must be one of {L.READINESS}")
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        node = _find_node(topic, args.id)
        node["readiness"] = args.value
        node["readiness_note"] = args.reason
        if args.value != "unknown" and node.get("coverage") != "covered":
            node["coverage"] = "covered"
            node.setdefault("covered_at", L.ts())
        topic["next"] = next_text(topic, slug)
        _touch(topic, "readiness", f"{args.id} -> {args.value}: {args.reason}")
        _save(st, f"{args.id} readiness set to {args.value}. NEXT: {topic['next']}")


def cmd_scope(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        node = _find_node(topic, args.id)
        node["required"] = bool(args.required)
        topic["next"] = next_text(topic, slug)
        _touch(topic, "scope", f"{args.id} {'required' if args.required else 'optional'}: {args.reason}")
        _save(st, f"{args.id} is now {'required' if args.required else 'optional'}. NEXT: {topic['next']}")


def cmd_next(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        topic["next"] = args.text
        _touch(topic, "next", args.text)
        _save(st, "Next step recorded.")


def cmd_checkpoint(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        _touch(topic, "checkpoint", args.text)
        _save(st, f"Checkpoint saved for '{slug}' at {L.fmt_local(topic['updated'])}.")


def cmd_correction(args):
    """Record a correction to taught material (label, key, claim) so the audit trail survives."""
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        entry = {"date": L.today(), "what": args.what, "why": args.why, "node": args.node or "", "card": args.card or "",
                 "sources": [s for s in (args.sources or "").split(",") if s]}
        topic.setdefault("corrections", []).append(entry)
        _touch(topic, "correction", f"{args.node or args.card or ''}: {args.what}")
        _save(st, f"Correction recorded ({len(topic['corrections'])} total).")


def cmd_node_edit(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        node = _find_node(topic, args.id)
        changes = []
        if args.label:
            changes.append(f"label: {node['label']!r} -> {args.label!r}")
            node["label"] = args.label
        if args.why is not None:
            node["why"] = args.why
            changes.append("why updated")
        if args.depends is not None:
            node["depends"] = [d.strip() for d in args.depends.split(",") if d.strip()]
            L.validate_plan(_nodes(topic))
            changes.append(f"depends: {node['depends']}")
        if not changes:
            raise L.LearnError("nothing to change (use --label, --why or --depends)")
        _touch(topic, "node-edit", f"{args.id}: {'; '.join(changes)}" + (f" ({args.reason})" if args.reason else ""))
        _save(st, f"{args.id} edited: " + "; ".join(changes))


# --- preparation ------------------------------------------------------------------------

def cmd_prep_topic(args):
    data = _stdin_json()
    L.validate_topic_prep(data)
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        ids = {n["id"] for n in _nodes(topic)}
        for ch in data["chunks"]:
            unknown = [i for i in ch["nodes"] if i not in ids]
            if unknown:
                raise L.ValidationError(f"chunk {ch['id']} names unknown nodes {unknown}")
        for x in data["exit_criteria"]:
            unknown = [i for i in x.get("nodes", []) if i not in ids]
            if unknown:
                raise L.ValidationError(f"exit criterion {x['id']} names unknown nodes {unknown}")
        data.setdefault("verified", L.today())
        # Documents registered with source-add survive a topic re-prep (their digest and hash live here).
        old_docs = {x["id"]: x for x in topic.get("prep", {}).get("sources", []) if x.get("kind") == "document"}
        data["sources"] = [dict(old_docs.pop(x["id"]), **x) if x["id"] in old_docs else x for x in data["sources"]]
        data["sources"] += list(old_docs.values())
        topic["prep"] = data
        _touch(topic, "prep-topic", f"{len(data['chunks'])} chunks, {len(data['exit_criteria'])} exit criteria, {len(data['sources'])} sources")
        _save(st, f"Topic preparation recorded: {len(data['chunks'])} chunk(s), {len(data['exit_criteria'])} exit criteria, {len(data['sources'])} source(s).")


def cmd_prep_node(args):
    data = _stdin_json()
    if data.get("id") and data["id"] != args.id:
        raise L.ValidationError(f"prep id {data['id']} != {args.id}")
    data["id"] = args.id
    L.validate_node_prep(data)
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        node = _find_node(topic, args.id)
        ids = {n["id"] for n in _nodes(topic)}
        for p in data.get("prerequisites", []):
            pid = p.get("id") if isinstance(p, dict) else p
            if pid not in ids:
                raise L.ValidationError(f"prerequisite {pid} is not a plan node")
        known_sources = {s["id"] for s in topic.get("prep", {}).get("sources", [])}
        cited = [r for c in data.get("claims", []) for r in c.get("sources", [])]
        cited += [r.get("source", "") for r in data.get("source_refs", []) if isinstance(r, dict)]
        missing = sorted({L.split_source_ref(r)[0] for r in cited} - known_sources)
        if missing:
            print(f"warning: claims cite sources not in the topic registry: {missing}", file=sys.stderr)
        data.setdefault("label", node["label"])
        data["saved"] = L.ts()
        L.write_json(node_prep_path(slug, args.id), data)
        node["prepared"] = True
        node["prep_status"] = data["status"]
        topic["next"] = next_text(topic, slug) if topic.get("status") == "teaching" else topic.get("next", "")
        _touch(topic, "prep-node", f"{args.id}: {data['status']}, {len(data['checks'])} check(s)")
        _save(st, f"Prepared {args.id} ({data['status']}): {len(data['checks'])} check(s), {len(data.get('claims', []))} claim(s), "
                  f"{len(data.get('misconceptions', []))} misconception(s). File: {L.rel(node_prep_path(slug, args.id))}")


def _fmt_check(c: dict, keys: bool) -> list[str]:
    out = [f"  check {c['id']} [{c['type']}, {c.get('role','normal')}{', load-bearing' if c.get('load_bearing') else ''}"
           f"{', review card' if c.get('review') else ''}] variants: " + ", ".join(v["id"] for v in c["variants"])]
    if c.get("exercise"):
        out.append(f"    exercise: {c['exercise']}")
    if keys:
        for v in c["variants"]:
            out.append(f"    {v['id']}: Q: {v['question'][:160]}")
            if v.get("code"):
                out.append("       code: " + v["code"].strip().replace("\n", " ⏎ ")[:160])
            out.append(f"       A: {v['answer'][:200]}")
            if v.get("required"):
                out.append("       required: " + " | ".join(v["required"]))
            if v.get("disqualifying"):
                out.append("       disqualifying: " + " | ".join(v["disqualifying"]))
        if c.get("hints"):
            out.append("    hints: " + " → ".join(h[:80] for h in c["hints"]))
    return out


def cmd_prep_show(args):
    state = L.load_state()
    slug, topic = _topic(state)
    prep = load_node_prep(slug, args.id)
    if prep is None:
        print(f"{args.id} has no prepared material. Prepare it: python3 scripts/state.py prep-node {args.id} < node.json")
        return
    node = _find_node(topic, args.id)
    print(f"{args.id} · {node['label']}  [{prep.get('status')}; verified {prep.get('verified') or 'no'}]")
    print(node_context(topic, args.id).splitlines()[1])
    print(f"Objective: {prep['objective']}")
    if prep.get("why_needed"):
        print(f"Why now: {prep['why_needed']}")
    if prep.get("motivation"):
        print(f"Motivation: {prep['motivation']}")
    if prep.get("outline"):
        print("Outline:")
        for i, step in enumerate(prep["outline"], 1):
            print(f"  {i}. {step}")
    if prep.get("claims"):
        print("Claims (kind · scope/boundary · sources):")
        for c in prep["claims"]:
            extra = f" · {c['boundary']}" if c.get("boundary") else ""
            src = f" [{', '.join(c.get('sources', []))}]" if c.get("sources") else ""
            print(f"  - ({c['kind']}) {c['text']}{extra}{src}")
    if prep.get("source_refs"):
        print("Source pages: " + "; ".join(f"{r.get('source')} {r.get('pages', '')}".strip() + (f" ({r['note']})" if r.get("note") else "")
                                          for r in prep["source_refs"] if isinstance(r, dict)))
    if prep.get("misconceptions"):
        print("Misconceptions → repair:")
        for m in prep["misconceptions"]:
            print(f"  - {m.get('id','')}: {m['text']} → {m.get('repair','')}")
    print("Checks" + (" (keys shown)" if args.keys else " (keys hidden; --keys to grade, `ask` to pose)") + ":")
    for c in prep["checks"]:
        for line in _fmt_check(c, args.keys):
            print(line)
    if prep.get("code_exercise"):
        ce = prep["code_exercise"]
        print(f"Code exercise: {ce.get('name','')} — {ce.get('summary', '')}" + (f" (folder {ce['folder']})" if ce.get("folder") else ""))
    if prep.get("review_suitability"):
        print(f"Review: {prep['review_suitability']}")


def cmd_prep_status(args):
    state = L.load_state()
    slug, topic = _topic(state)
    tp = topic.get("prep", {})
    print(f"Topic prep: capability {'set' if tp.get('capability') else 'MISSING'} · chunks {len(tp.get('chunks', []))} · "
          f"exit criteria {len(tp.get('exit_criteria', []))} · sources {len(tp.get('sources', []))} · verified {tp.get('verified') or 'no'}")
    for src in _documents(topic):
        print(f"  document {src['id']} ({src.get('role')}): {_doc_status(slug, src)}")
    chunk = current_chunk(topic)
    info = eligible(topic)
    rec = info["recommended"]["id"] if info["recommended"] else None
    for n in _nodes(topic):
        prep = load_node_prep(slug, n["id"])
        tag = "-" if prep is None else f"{prep.get('status')}, {len(prep['checks'])} check(s), verified {prep.get('verified') or 'no'}"
        flag = ""
        if chunk and n["id"] in chunk["nodes"] and prep is None and n.get("coverage") != "covered":
            flag = "  <- in the current chunk, not prepared"
        if n["id"] == rec:
            flag += "  <- next to teach"
        print(f"  {n['id']:5} {n.get('coverage','pending'):8} {n.get('readiness','unknown'):13} prep: {tag}{flag}")


# --- documents (PDFs and other local sources) ------------------------------------------

def _documents(topic: dict) -> list[dict]:
    return [x for x in topic.get("prep", {}).get("sources", []) if x.get("kind") == "document"]


def _doc_file(src: dict):
    return L.resolve(src["path"])


def _doc_status(slug: str, src: dict) -> str:
    path = _doc_file(src)
    if not path.exists():
        return f"FILE MISSING ({src['path']})"
    if not src.get("digested") or not L.source_digest_path(slug, src["id"]).exists():
        return "not digested yet (run the document-reader, then source-digest)"
    if L.file_sha256(path) != src.get("digest_sha256"):
        return f"FILE CHANGED since the digest of {src['digested']}: re-digest and recheck the nodes that cite it"
    return "digested, unchanged"


def _find_document(topic: dict, source_id: str) -> dict:
    for src in _documents(topic):
        if src["id"] == source_id:
            return src
    known = ", ".join(x["id"] for x in _documents(topic)) or "none"
    raise L.LearnError(f"no document source '{source_id}' (registered: {known}). Add it: source-add PATH")


def cmd_source_add(args):
    path = L.resolve(args.path)
    if not path.exists():
        alt = L.dir_path("resourcesDir") / args.path
        if alt.exists():
            path = alt
    if not path.is_file():
        raise L.LearnError(f"no such file: {args.path} (put documents in {L.rel(L.dir_path('resourcesDir'))}/)")
    sid = args.id or (re.sub(r"[^A-Za-z0-9_-]+", "-", path.stem).strip("-_")[:32] or "doc")
    if not sid[0].isalpha():
        sid = "d" + sid[:31]
    try:
        stored = str(path.resolve().relative_to(L.ROOT))
    except ValueError:
        stored = str(path)
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        prep = topic.setdefault("prep", {})
        L.validate_topic_prep(prep)
        sha = L.file_sha256(path)
        old = next((x for x in prep["sources"] if x["id"] == sid), None)
        if old is not None and old.get("kind") != "document":
            raise L.LearnError(f"source id '{sid}' is already a web source; pick another with --id")
        entry = dict(old or {})
        entry.update({"id": sid, "kind": "document", "path": stored, "sha256": sha, "bytes": path.stat().st_size,
                      "page_count": L.pdf_page_count(path), "added": entry.get("added") or L.today()})
        entry["title"] = args.title or entry.get("title") or path.stem
        entry["role"] = args.role or entry.get("role") or "primary"
        if args.pages is not None:
            entry["pages"] = args.pages
        entry.setdefault("pages", "")
        entry.setdefault("digested", "")
        entry.setdefault("digest_sha256", "")
        if old is None:
            prep["sources"].append(entry)
        else:
            old.clear()
            old.update(entry)
        L.validate_topic_prep(prep)
        _touch(topic, "source-add", f"{sid} ({entry['role']}): {stored}")
        pages = f", {entry['page_count']} page(s)" if entry["page_count"] else ""
        scope = f", scope pages {entry['pages']}" if entry["pages"] else ""
        _save(st, f"Document '{sid}' registered ({entry['role']}{pages}{scope}): {stored}. {_doc_status(slug, entry)}")


def cmd_source_digest(args):
    data = _stdin_json()
    L.validate_source_digest(data)
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        src = _find_document(topic, args.id)
        path = _doc_file(src)
        if not path.exists():
            raise L.LearnError(f"{src['path']} is missing; cannot tie the digest to a file version")
        ids = {n["id"] for n in _nodes(topic)}
        proposed = sorted({m["node"] for m in data["node_map"]} - ids)
        if proposed:
            print(f"note: node_map names nodes not in the plan yet: {proposed} (add them with node-add if you adopt them)", file=sys.stderr)
        data.update({"source": args.id, "sha256": L.file_sha256(path), "saved": L.ts()})
        L.write_json(L.source_digest_path(slug, args.id), data)
        src["digested"] = L.today()
        src["digest_sha256"] = data["sha256"]
        _touch(topic, "source-digest", f"{args.id}: {len(data['sections'])} sections, {len(data['conflicts'])} conflict(s)")
        _save(st, f"Digest of '{args.id}' saved: {len(data['sections'])} section(s), {len(data['objectives'])} objective(s), "
                  f"{len(data['node_map'])} node mapping(s), {len(data['conflicts'])} flagged conflict(s).")


def cmd_source_show(args):
    state = L.load_state()
    slug, topic = _topic(state)
    docs = _documents(topic)
    if args.id:
        docs = [_find_document(topic, args.id)]
    if not docs:
        print("No documents registered. Put the file in resources/ and run: python3 scripts/state.py source-add resources/<file>.pdf --role primary")
        return
    shown = 0
    for src in docs:
        digest = L.read_json(L.source_digest_path(slug, src["id"]), None)
        if args.node:
            if not digest:
                continue
            maps = [m for m in digest["node_map"] if m["node"] == args.node]
            secs = [x for x in digest["sections"] if args.node in x.get("nodes", [])]
            if not maps and not secs:
                continue
            shown += 1
            print(f"{src['id']} ({src.get('role')}) for {args.node}:")
            for m in maps:
                print(f"  pages {m.get('pages', '?')}: {m.get('focus', '')}" + (f" [depth: {m['depth']}]" if m.get("depth") else ""))
            for x in secs:
                print(f"  § {x['id']} {x['title']} (pages {x.get('pages', '?')})")
            for c in digest["conflicts"]:
                if args.node in c.get("nodes", []):
                    print(f"  ! conflict p{c.get('pages', '?')}: {c['claim']} — {c['issue']}" + (f" → {c['resolution']}" if c.get("resolution") else ""))
            continue
        print(f"{src['id']} · {src.get('title')} ({src.get('role')}; {src['path']}"
              + (f"; scope pages {src['pages']}" if src.get("pages") else "") + f") — {_doc_status(slug, src)}")
        if not digest or not args.id:
            continue
        print(f"Summary: {digest['summary']}")
        if digest.get("scope_role"):
            print(f"Role in scope: {digest['scope_role']}")
        if digest["objectives"]:
            print("Objectives: " + "; ".join(digest["objectives"]))
        print("Sections:")
        for x in digest["sections"]:
            nodes = f" → {', '.join(x['nodes'])}" if x.get("nodes") else ""
            depth = f" [{x['depth']}]" if x.get("depth") else ""
            print(f"  § {x['id']} {x['title']} (pages {x.get('pages', '?')}){depth}{nodes}")
        if digest["prerequisites_outside"]:
            print("Prerequisites it assumes: " + "; ".join(map(str, digest["prerequisites_outside"])))
        if digest["conflicts"]:
            print("Flagged conflicts:")
            for c in digest["conflicts"]:
                print(f"  ! p{c.get('pages', '?')}: {c['claim']} — {c['issue']}" + (f" → {c['resolution']}" if c.get("resolution") else " (unresolved)"))
    if args.node and not shown:
        print(f"No digested document maps to {args.node}.")


# --- interactions ------------------------------------------------------------------------

def _pick_variant(check: dict, attempts: list[dict], want: str | None, node: str = "") -> dict:
    variants = check["variants"]
    if want:
        for v in variants:
            if v["id"] == want:
                return v
        raise L.LearnError(f"check {check['id']} has no variant {want!r}")
    last: dict[str, str] = {}
    for a in attempts:
        if a.get("check") == check["id"] and (not node or a.get("node") == node):
            last[a.get("variant", "")] = max(last.get(a.get("variant", ""), ""), a.get("ts", ""))
    return min(variants, key=lambda v: (last.get(v["id"], ""), v["id"]))


def _question_text(ptype: str, variant: dict, order: list[str] | None) -> str:
    out = [variant["question"].strip()]
    if variant.get("code"):
        out.append("```c\n" + variant["code"].rstrip() + "\n```")
    if ptype == "mcq":
        opts = order or variant.get("options", [])
        out.append("\n".join(f"{chr(65 + i)}) {o}" for i, o in enumerate(opts)))
    return "\n\n".join(out)


def cmd_ask(args):
    adhoc = _stdin_json() if args.adhoc else None
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        p = topic.get("pending")
        if p and p.get("stage") != "completed" and not args.replace:
            raise L.LearnError(f"pending interaction {p['id']} is still {p['stage']} ({p['node']} {p['check']}/{p['variant']}). "
                               f"Grade it with `record`, show it with `pending`, or pass --replace to abandon it.")
        node = _find_node(topic, args.node)
        attempts = topic.get("attempts", [])
        exit_id = args.exit or ""
        if adhoc:
            check = {"id": args.check or f"adhoc-{len(attempts) + 1}", "type": adhoc.get("type", "short"), "role": "normal",
                     "variants": [dict(adhoc, id=adhoc.get("id", "v1"))], "hints": adhoc.get("hints", []),
                     "load_bearing": adhoc.get("load_bearing", adhoc.get("type", "short") != "mcq"),
                     "review": adhoc.get("review", False), "kind": adhoc.get("kind", "concept")}
            L.validate_check(check, "adhoc")
            variant = check["variants"][0]
        else:
            if exit_id:
                _, checks = exit_checks(topic, exit_id)
            else:
                checks = all_checks(topic, slug, args.node)
            if not checks:
                raise L.LearnError(f"{args.node} has no prepared checks. Prepare it (prep-node) or pass --adhoc with the question JSON on stdin.")
            if args.check:
                check = next((c for c in checks if c["id"] == args.check), None)
                if check is None:
                    raise L.LearnError(f"no check {args.check!r}; known: {[c['id'] for c in checks]}")
            elif args.fresh:
                check = next((c for c in checks if c.get("role") == "fresh"), None)
                if check is None:
                    raise L.LearnError("no fresh variant prepared for this node")
            else:
                asked = {a.get("check") for a in attempts if a.get("node") == args.node}
                check = next((c for c in checks if c.get("role") == "normal" and c["id"] not in asked), None) \
                    or next((c for c in checks if c.get("role") == "normal"), None) or checks[0]
            variant = _pick_variant(check, attempts, args.variant, args.node)
        prior = [a for a in attempts if a.get("check") == check["id"] and a.get("node") == args.node]
        kind = args.kind or ("exit" if exit_id else ("practice" if any(a["ts"][:10] == L.today() for a in prior) else "initial"))
        pid = L.new_id("p", {a.get("pending", "") for a in attempts})
        order = None
        if check["type"] == "mcq":
            opts = [o for o in variant.get("options", []) if o.strip().lower() != "i don't know"]
            rnd = random.Random(pid)
            rnd.shuffle(opts)
            order = opts + ["I don't know"]
        pending = {
            "id": pid, "type": check["type"], "topic": slug, "node": args.node, "check": check["id"], "variant": variant["id"],
            "rubric_version": int(variant.get("rubric_version", 1)), "kind": kind, "exit": exit_id,
            "params": {"order": order} if order else {}, "stage": "awaiting", "assistance": [], "asked_at": L.ts(),
            "response": None, "last_attempt": None, "question_head": variant["question"][:120],
            "exercise": check.get("exercise", ""), "hints_total": len(check.get("hints", [])),
        }
        if adhoc:
            pending["inline"] = check
        topic["pending"] = pending
        topic["next"] = (f"Waiting for the learner's answer to {pid} ({args.node} {check['id']}/{variant['id']}, {check['type']}); "
                         f"then grade it: python3 scripts/state.py record < result.json")
        _touch(topic, "ask", f"{pid} {args.node} {check['id']}/{variant['id']} {check['type']} {kind}")
        text = _question_text(check["type"], variant, order)
        st.commit()
        write_progress(st.state)
        print(f"[{pid} · {args.node} · {check['id']}/{variant['id']} · {check['type']} · {kind} · key v{pending['rubric_version']}"
              + (f" · exercise {check['exercise']}" if check.get("exercise") else "") + "]")
        print()
        print(text)


def _resolve_variant(topic: dict, slug: str, p: dict) -> tuple[dict, dict]:
    if p.get("inline"):
        check = p["inline"]
    else:
        checks = exit_checks(topic, p["exit"])[1] if p.get("exit") else all_checks(topic, slug, p["node"])
        check = next((c for c in checks if c["id"] == p["check"]), None)
        if check is None:
            raise L.LearnError(f"prepared check {p['check']} for {p['node']} no longer exists")
    variant = next((v for v in check["variants"] if v["id"] == p["variant"]), None)
    if variant is None:
        raise L.LearnError(f"variant {p['variant']} of check {p['check']} no longer exists")
    return check, variant


def cmd_pending(args):
    state = L.load_state()
    slug, topic = _topic(state)
    p = topic.get("pending")
    if not p or p.get("stage") == "completed":
        print("No pending interaction. NEXT: " + (topic.get("next") or ""))
        return
    check, variant = _resolve_variant(topic, slug, p)
    print(pending_line(topic).splitlines()[0])
    print()
    print(_question_text(p["type"], variant, p.get("params", {}).get("order")))
    if p.get("response"):
        print("\nRecorded answer:\n" + p["response"])
    if p.get("assistance"):
        print("\nAssistance given: " + ", ".join(p["assistance"]))
    if args.keys or p["stage"] == "recorded":
        print("\n-- grading key (do not show the learner) --")
        print("Answer: " + variant["answer"])
        if variant.get("required"):
            print("Required: " + " | ".join(variant["required"]))
        if variant.get("accepted"):
            print("Accepted alternatives: " + " | ".join(variant["accepted"]))
        if variant.get("disqualifying"):
            print("Disqualifying: " + " | ".join(variant["disqualifying"]))
        if check.get("hints"):
            print("Hint ladder: " + " → ".join(check["hints"]))
    if p["stage"] == "awaiting":
        print("\nStage: awaiting. If the learner has not answered, show the question above again; do not ask a different one.")
    else:
        print("\nStage: recorded. Grade the recorded answer now with `record`; do not re-ask.")


def cmd_answer(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        p = topic.get("pending")
        if not p or p.get("stage") == "completed":
            raise L.LearnError("no pending interaction to answer")
        text = args.text or ""
        if args.file:
            text = L.resolve(args.file).read_text("utf-8")
        p["response"] = text.strip()[:2000]
        p["stage"] = "recorded"
        p["answered_at"] = L.ts()
        _touch(topic, "answer", f"{p['id']} answer recorded ({len(p['response'])} chars)")
        _save(st, f"{p['id']}: answer recorded; grade it with record.")


def cmd_hint(args):
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        p = topic.get("pending")
        if not p or p.get("stage") == "completed":
            raise L.LearnError("no pending interaction")
        check, _ = _resolve_variant(topic, slug, p)
        ladder = ["nudge", "substep", "worked"]
        given = p.setdefault("assistance", [])
        level = args.level or (ladder[len(given)] if len(given) < len(ladder) else "worked")
        given.append(level)
        hints = check.get("hints", [])
        idx = ladder.index(level) if level in ladder else len(ladder) - 1
        text = hints[idx] if idx < len(hints) else ""
        _touch(topic, "hint", f"{p['id']} {level}")
        st.commit()
        write_progress(st.state)
        print(f"[assistance recorded: {level}; {len(given)} hint(s) so far]")
        print(text if text else "(no prepared hint at this level; give the smallest hint that unblocks)")


def _derive_quality(result: str, independent: bool, required_met_all: bool, given: int | None) -> tuple[int, str]:
    if result == "unknown":
        return 0, ""
    if result == "fail":
        return min(given if given is not None else 1, 2), ""
    if result == "partial":
        return min(given if given is not None else 2, 2), ""
    q = given if given is not None else 4
    if not independent:
        return min(q, 2), "assisted"
    if not required_met_all:
        return min(q, 2), "missing required point"
    return max(q, 3), ""


def cmd_record(args):
    data = _stdin_json()
    with L.Store(write=True) as st:
        slug, topic = _topic(st.state)
        op = data.get("op")
        if st.already_applied(op):
            print(f"op {op} already applied; nothing changed")
            return
        p = topic.get("pending")
        if not p:
            raise L.LearnError("no pending interaction; pose the question with `ask` first")
        if p.get("stage") == "completed":
            raise L.LearnError(f"pending {p['id']} was already recorded as attempt {p.get('last_attempt')}; ask a new question")
        result = data.get("result")
        if result not in L.RESULTS:
            raise L.LearnError(f"result must be one of {L.RESULTS}")
        check, variant = _resolve_variant(topic, slug, p)
        node = _find_node(topic, p["node"])
        assistance = data.get("assistance")
        if assistance is None:
            given = p.get("assistance", [])
            assistance = max(given, key=lambda a: L.ASSISTANCE.index(a)) if given else "none"
        if assistance not in L.ASSISTANCE:
            raise L.LearnError(f"assistance must be one of {L.ASSISTANCE}")
        independent = assistance in L.INDEPENDENT_ASSISTANCE
        required = list(variant.get("required", []))
        met = data.get("required_met")
        missed = data.get("required_missed")
        if met is None and missed is None:
            met = required if result == "pass" else []
            missed = [] if result == "pass" else required
        met, missed = list(met or []), list(missed or [])
        unknown = [x for x in met + missed if required and x not in required]
        if unknown:
            raise L.LearnError(f"required points not in the key: {unknown}. Key: {required}")
        if result == "pass" and missed:
            result = "partial"
        quality, capped = _derive_quality(result, independent, not missed, data.get("quality"))
        if data.get("quality") is not None and int(data["quality"]) != quality and capped:
            capped = f"{capped} (teacher said {data['quality']})"
        if p.get("response") is None and data.get("response"):
            p["response"] = str(data["response"]).strip()[:2000]
        attempt = {
            "id": L.new_id("a", {a["id"] for a in topic.get("attempts", [])}), "ts": L.ts(), "pending": p["id"],
            "node": p["node"], "check": p["check"], "variant": p["variant"], "rubric_version": p["rubric_version"],
            "kind": p.get("kind", "initial"), "exit": p.get("exit", ""), "response": (p.get("response") or "")[:400],
            "result": result, "required_met": met, "required_missed": missed, "assistance": assistance,
            "independent": independent, "misconception": data.get("misconception", ""), "quality": quality,
            "note": data.get("note", ""), "card": "", "op": op or "",
        }
        if capped:
            attempt["capped"] = capped
        # readiness
        override = data.get("readiness")
        if override:
            if override not in L.READINESS:
                raise L.LearnError(f"readiness must be one of {L.READINESS}")
            if not data.get("reason"):
                raise L.LearnError("an explicit readiness needs a short reason")
            readiness, why = override, data["reason"]
        elif result == "pass" and independent:
            if check["type"] == "mcq" and check.get("load_bearing", False):
                readiness, why = "provisional", "multiple choice alone does not show independent reproduction"
            else:
                readiness, why = "ready", f"independent pass on {check['id']}/{variant['id']}"
        elif result == "pass":
            readiness, why = "provisional", f"passed with help ({assistance})"
        else:
            readiness, why = "needs_repair", (attempt["misconception"] or f"{result} on {check['id']}: missed " + ", ".join(missed))
        covered = data.get("covered", True)
        if covered and attempt["kind"] != "review":
            node["coverage"] = "covered"
            node.setdefault("covered_at", L.ts())
            node["done_at"] = node.get("done_at") or L.ts()
            node["check"] = check["type"]
        if attempt["kind"] == "review":
            node["retention"] = "demonstrated" if result == "pass" and independent else "needs_review"
        else:
            node["readiness"] = readiness
            node["readiness_note"] = why
        if data.get("summary"):
            node["summary"] = data["summary"]
        elif attempt["kind"] != "review":
            node["summary"] = (f"{check['id']}/{variant['id']} {result} q{quality}" + (f", help {assistance}" if assistance != 'none' else "")
                               + (f"; {attempt['misconception']}" if attempt["misconception"] else ""))
        if data.get("revisit"):
            node["revisit"] = data["revisit"]
        # card
        card_msg = "no card"
        promote = data.get("promote", check.get("review", False)) and not p.get("inline") or data.get("promote") is True
        if promote:
            card = R.find_by_check(st.deck, slug, p["node"], check["id"])
            if card is None:
                card = R.card_from_check(slug, p["node"], check, {c["id"] for c in st.deck["cards"]})
                st.deck["cards"].append(card)
                card_msg = f"card {card['id']} created"
            else:
                card_msg = f"card {card['id']}"
            skind = attempt["kind"] if attempt["kind"] in L.ATTEMPT_KINDS else "initial"
            outcome = R.apply_grade(card, quality, L.today(), kind=skind, independent=independent, required_met=not missed,
                                    note=attempt["misconception"] or data.get("note", ""), variant=variant["id"], op=op)
            card.pop("needs_replacement_check", None)
            attempt["card"] = card["id"]
            card_msg += f" graded {outcome['q']}: {outcome['reason']}; due {outcome['due']}"
        topic.setdefault("attempts", []).append(attempt)
        L.validate_attempt(attempt)
        p["stage"] = "completed"
        p["last_attempt"] = attempt["id"]
        topic["next"] = data.get("next") or (
            f"Repair {p['node']}: {why}" if readiness == "needs_repair" and attempt["kind"] != "review" else next_text(topic, slug))
        _touch(topic, "record", f"{attempt['id']} {p['node']} {check['id']}/{variant['id']} {result} q{quality} help={assistance} -> {readiness}")
        _save(st, "\n".join([
            f"{attempt['id']}: {p['node']} {check['id']}/{variant['id']} {result}, quality {quality}"
            + (f" (capped: {capped})" if capped else "") + f", help {assistance}",
            f"{p['node']} readiness -> {node.get('readiness')}" + (f" ({why})" if attempt["kind"] != "review" else f"; retention {node.get('retention')}"),
            card_msg,
            "NEXT: " + topic["next"],
        ] + ([_next_context(topic, slug)] if readiness != "needs_repair" and _next_context(topic, slug) else [])), op=op)


def _next_context(topic: dict, slug: str) -> str:
    info = eligible(topic)
    rec = info["recommended"]
    if rec is None:
        return ""
    prep = load_node_prep(slug, rec["id"])
    if prep is None:
        return f"Next node {rec['id']} · {rec['label']} is not prepared yet."
    checks = ", ".join(f"{c['id']} ({c['type']})" for c in prep["checks"])
    return f"Next node {rec['id']} · {rec['label']}\n  objective: {prep['objective']}\n  checks: {checks}"


# --- main ----------------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("show"); p.add_argument("--full", action="store_true"); p.set_defaults(fn=cmd_show)
    sub.add_parser("topics").set_defaults(fn=cmd_topics)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)
    sub.add_parser("migrate").set_defaults(fn=cmd_migrate)
    p = sub.add_parser("backup"); p.add_argument("--label"); p.set_defaults(fn=cmd_backup)
    p = sub.add_parser("restore"); p.add_argument("file", nargs="?"); p.add_argument("--list", action="store_true"); p.set_defaults(fn=cmd_restore)
    p = sub.add_parser("history"); p.add_argument("--node"); p.add_argument("--limit", type=int, default=20); p.set_defaults(fn=cmd_history)

    p = sub.add_parser("start"); p.add_argument("title"); p.add_argument("--goal"); p.add_argument("--slug"); p.set_defaults(fn=cmd_start)
    p = sub.add_parser("goal"); p.add_argument("text"); p.set_defaults(fn=cmd_goal)
    p = sub.add_parser("edge"); p.add_argument("text"); p.set_defaults(fn=cmd_edge)
    sub.add_parser("pause").set_defaults(fn=cmd_pause)
    p = sub.add_parser("resume"); p.add_argument("slug"); p.set_defaults(fn=cmd_resume)
    p = sub.add_parser("stop"); p.add_argument("--summary"); p.set_defaults(fn=cmd_stop)
    p = sub.add_parser("finish"); p.add_argument("--summary"); p.set_defaults(fn=cmd_finish)
    p = sub.add_parser("log-target"); p.add_argument("path", nargs="?"); p.add_argument("--clear", action="store_true"); p.set_defaults(fn=cmd_log_target)

    sub.add_parser("plan-set").set_defaults(fn=cmd_plan_set)
    p = sub.add_parser("plan-show"); p.add_argument("node", nargs="?"); p.set_defaults(fn=cmd_plan_show)
    sub.add_parser("plan-approve").set_defaults(fn=cmd_plan_approve)
    p = sub.add_parser("node-add"); p.add_argument("id"); p.add_argument("label"); p.add_argument("--depends"); p.add_argument("--optional", action="store_true"); p.set_defaults(fn=cmd_node_add)
    sub.add_parser("next-node").set_defaults(fn=cmd_next_node)
    p = sub.add_parser("node-done"); p.add_argument("id"); p.add_argument("summary"); p.add_argument("--check", choices=["short", "mcq", "code", "none"])
    p.add_argument("--readiness", choices=["ready", "provisional"]); p.set_defaults(fn=cmd_node_done)
    p = sub.add_parser("node-shaky"); p.add_argument("id"); p.add_argument("why"); p.set_defaults(fn=cmd_node_shaky)
    p = sub.add_parser("readiness"); p.add_argument("id"); p.add_argument("value"); p.add_argument("--reason", required=True); p.set_defaults(fn=cmd_readiness)
    p = sub.add_parser("scope"); p.add_argument("id"); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--optional", dest="required", action="store_false"); g.add_argument("--required", dest="required", action="store_true")
    p.add_argument("--reason", required=True); p.set_defaults(fn=cmd_scope)
    p = sub.add_parser("node-edit"); p.add_argument("id"); p.add_argument("--label"); p.add_argument("--why"); p.add_argument("--depends"); p.add_argument("--reason"); p.set_defaults(fn=cmd_node_edit)
    p = sub.add_parser("correction"); p.add_argument("what"); p.add_argument("why"); p.add_argument("--node"); p.add_argument("--card"); p.add_argument("--sources"); p.set_defaults(fn=cmd_correction)
    p = sub.add_parser("next"); p.add_argument("text"); p.set_defaults(fn=cmd_next)
    p = sub.add_parser("checkpoint"); p.add_argument("text"); p.set_defaults(fn=cmd_checkpoint)

    sub.add_parser("prep-topic").set_defaults(fn=cmd_prep_topic)
    p = sub.add_parser("prep-node"); p.add_argument("id"); p.set_defaults(fn=cmd_prep_node)
    p = sub.add_parser("prep-show"); p.add_argument("id"); p.add_argument("--keys", action="store_true"); p.set_defaults(fn=cmd_prep_show)
    sub.add_parser("prep-status").set_defaults(fn=cmd_prep_status)
    p = sub.add_parser("source-add"); p.add_argument("path"); p.add_argument("--id"); p.add_argument("--title")
    p.add_argument("--role", choices=L.SOURCE_ROLES); p.add_argument("--pages"); p.set_defaults(fn=cmd_source_add)
    p = sub.add_parser("source-digest"); p.add_argument("id"); p.set_defaults(fn=cmd_source_digest)
    p = sub.add_parser("source-show"); p.add_argument("id", nargs="?"); p.add_argument("--node"); p.set_defaults(fn=cmd_source_show)

    p = sub.add_parser("ask"); p.add_argument("node"); p.add_argument("--check"); p.add_argument("--variant"); p.add_argument("--fresh", action="store_true")
    p.add_argument("--kind", choices=list(L.ATTEMPT_KINDS)); p.add_argument("--exit"); p.add_argument("--adhoc", action="store_true"); p.add_argument("--replace", action="store_true")
    p.set_defaults(fn=cmd_ask)
    p = sub.add_parser("pending"); p.add_argument("--keys", action="store_true"); p.set_defaults(fn=cmd_pending)
    p = sub.add_parser("answer"); p.add_argument("text", nargs="?"); p.add_argument("--file"); p.set_defaults(fn=cmd_answer)
    p = sub.add_parser("hint"); p.add_argument("--level", choices=["nudge", "substep", "worked"]); p.set_defaults(fn=cmd_hint)
    sub.add_parser("record").set_defaults(fn=cmd_record)

    args = parser.parse_args(argv)
    L.cli_main(lambda: args.fn(args))


if __name__ == "__main__":
    main()
