#!/usr/bin/env python3
"""Lesson state: the teacher's external memory.

The chat context is disposable. This file plus the lesson note are what
survive compaction, restarts and new sessions. Every command below mutates
state/state.json, rewrites state/progress.md (human-readable mirror) and
prints a one-line confirmation.

Usage (run from the repo root):
  python3 scripts/state.py show
  python3 scripts/state.py topics
  python3 scripts/state.py start "Title" [--goal "..."] [--slug slug]
  python3 scripts/state.py goal "what the learner actually wants"
  python3 scripts/state.py edge "strand: floor=..., ceiling=..."
  python3 scripts/state.py plan-set < plan.json      # {"nodes": [{"id","label","depends":[],"why":""}]}
  python3 scripts/state.py plan-show [NODE]          # generated mermaid map (ids in labels); NODE = local view
  python3 scripts/state.py plan-approve
  python3 scripts/state.py node-add ID "label" [--depends a,b]
  python3 scripts/state.py node-done ID "one-line summary" [--check short|mcq|code|none]
  python3 scripts/state.py node-shaky ID "why it did not land"
  python3 scripts/state.py next "the very next step"
  python3 scripts/state.py checkpoint "what just happened"
  python3 scripts/state.py pause
  python3 scripts/state.py resume SLUG
  python3 scripts/state.py finish [--summary "..."]
  python3 scripts/state.py log-target PATH | --clear
"""
from __future__ import annotations

import argparse
import json
import sys

import learnlib as L

MAX_LOG = 200
STATUSES = ("probing", "planning", "teaching", "paused", "finished")


def _topic(state: dict, slug: str | None = None) -> tuple[str, dict]:
    slug = slug or state.get("active_topic")
    if not slug or slug not in state["topics"]:
        sys.exit("error: no active topic. Run: python3 scripts/state.py start \"Title\"")
    return slug, state["topics"][slug]


def _touch(topic: dict, event: str, text: str = "") -> None:
    topic["updated"] = L.ts()
    topic.setdefault("log", []).append({"ts": L.ts(), "event": event, "text": text})
    if len(topic["log"]) > MAX_LOG:
        topic["log"] = topic["log"][-MAX_LOG:]


def _save(state: dict, message: str) -> None:
    L.save_state(state)
    write_progress(state)
    print(message)


# --- rendering ---------------------------------------------------------------

def _node_line(node: dict) -> str:
    mark = {"done": "✓", "shaky": "~", "pending": "·"}.get(node.get("status", "pending"), "·")
    check = node.get("check") or ""
    check = f" [{check}]" if check and check != "none" else ""
    summary = f" — {node['summary']}" if node.get("summary") else ""
    return f"{mark} {node['id']} {node.get('label', '')}{check}{summary}"


def _head(label: str) -> str:
    """The first clause of a label, for compact references."""
    for sep in (":", ";", " (", " - "):
        idx = label.find(sep)
        if idx >= 12:
            return label[:idx].strip()
    return label.strip()


def _short(label: str, width: int = 30, max_lines: int = 3) -> str:
    """Wrap a label onto up to max_lines lines for a mermaid box; ellipsis if longer."""
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
    """Deterministic map generated from the plan: ids in every label, edges from
    `depends`, done/shaky/current coloured. With `focus`, only that node, what it
    builds on and what builds on it."""
    plan = topic.get("plan") or {}
    nodes = plan.get("nodes", [])
    if not nodes:
        return plan.get("mermaid", "")
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
    done = [n["id"] for n in shown if n.get("status") == "done"]
    shaky = [n["id"] for n in shown if n.get("status") == "shaky"]
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
    """One line placing a node in the plan, for the teacher to paste when a node starts."""
    nodes = {n["id"]: n for n in topic.get("plan", {}).get("nodes", [])}
    node = nodes.get(node_id)
    if not node:
        return f"Node {node_id} is not in the plan."
    name = lambda i: f"{i} · {_head(nodes[i]['label'])}" if i in nodes else i  # noqa: E731
    builds_on = ", ".join(name(d) for d in node.get("depends", [])) or "nothing (a foundation)"
    leads_to = ", ".join(name(n["id"]) for n in nodes.values() if node_id in n.get("depends", [])) or "the goal directly"
    return f"**{node_id} · {node['label']}**\nBuilds on: {builds_on}.\nLeads to: {leads_to}."


def summary_text(state: dict, verbose: bool = False) -> str:
    """Compact summary used by hooks and /status. Aim for < 40 lines."""
    lines = []
    slug = state.get("active_topic")
    if slug and slug in state["topics"]:
        topic = state["topics"][slug]
        nodes = topic.get("plan", {}).get("nodes", [])
        done = [n for n in nodes if n.get("status") == "done"]
        shaky = [n for n in nodes if n.get("status") == "shaky"]
        pending = [n for n in nodes if n.get("status", "pending") == "pending"]
        lines.append(
            f"Active topic: {topic['title']} ({slug}) · status: {topic['status']} · "
            f"started {topic['started']} · last update {L.fmt_local(topic['updated'])}"
        )
        if topic.get("note"):
            lines.append(f"Lesson note: {L.rel(topic['note'])}")
        if topic.get("goal"):
            lines.append(f"Goal: {topic['goal']}")
        if topic.get("edge"):
            lines.append("Edge (what the learner has / where it runs out):")
            lines.extend(f"  - {e}" for e in topic["edge"][-6:])
        plan = topic.get("plan") or {}
        if nodes:
            approved = "approved" if plan.get("approved") else "NOT yet approved by the learner"
            lines.append(f"Plan ({approved}): {len(done)}/{len(nodes)} nodes done, {len(shaky)} shaky, {len(pending)} pending")
            for node in nodes:
                lines.append("  " + _node_line(node))
        elif topic["status"] in ("planning", "teaching"):
            lines.append("Plan: none recorded yet (run plan-set).")
        if topic.get("next"):
            lines.append(f"NEXT: {topic['next']}")
        log = topic.get("log", [])
        if log:
            last = log[-1]
            lines.append(f"Last checkpoint: {L.fmt_local(last['ts'])} · {last['event']}: {last['text']}")
    else:
        lines.append("No active topic.")
        recent = sorted(state["topics"].values(), key=lambda t: t.get("updated", ""), reverse=True)[:5]
        if recent:
            lines.append("Recent topics: " + "; ".join(f"{t['title']} ({t['status']}, {t['started']})" for t in recent))
    if state.get("log_target"):
        lines.append(f"Session log target: {L.rel(state['log_target'])}")
    return "\n".join(lines)


def write_progress(state: dict) -> None:
    out = [f"# Learning progress", f"_Updated {L.fmt_local(L.ts())}_", ""]
    slug = state.get("active_topic")
    if slug and slug in state["topics"]:
        topic = state["topics"][slug]
        out.append(f"## Active: {topic['title']} (`{slug}`) · {topic['status']}")
        out.append(f"- Started: {topic['started']} · Updated: {L.fmt_local(topic['updated'])}")
        if topic.get("note"):
            out.append(f"- Note: `{L.rel(topic['note'])}`")
        if topic.get("goal"):
            out.append(f"- Goal: {topic['goal']}")
        if topic.get("edge"):
            out.append("- Edge findings:")
            out.extend(f"  - {e}" for e in topic["edge"])
        if topic.get("next"):
            out.append(f"- **Next:** {topic['next']}")
        plan = topic.get("plan") or {}
        nodes = plan.get("nodes", [])
        if nodes:
            out.append("")
            out.append(f"### Plan ({'approved' if plan.get('approved') else 'not approved'})")
            out.append("| id | node | depends on | status | check | summary |")
            out.append("|---|---|---|---|---|---|")
            for n in nodes:
                out.append(
                    f"| {n['id']} | {n.get('label','')} | {', '.join(n.get('depends', []))} | "
                    f"{n.get('status','pending')} | {n.get('check','') or ''} | {n.get('summary','') or ''} |"
                )
        mermaid = plan_mermaid(topic)
        if mermaid:
            out.append("")
            out.append("```mermaid")
            out.append(mermaid.strip())
            out.append("```")
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
        out.append("| slug | title | status | started | finished | nodes done |")
        out.append("|---|---|---|---|---|---|")
        for s, t in sorted(state["topics"].items(), key=lambda kv: kv[1].get("updated", ""), reverse=True):
            nodes = t.get("plan", {}).get("nodes", [])
            done = sum(1 for n in nodes if n.get("status") == "done")
            out.append(f"| {s} | {t['title']} | {t['status']} | {t['started']} | {t.get('finished') or ''} | {done}/{len(nodes)} |")
    (L.dir_path("stateDir", create=True) / "progress.md").write_text("\n".join(out) + "\n", "utf-8")


# --- commands ----------------------------------------------------------------

def cmd_show(args, state):
    print(summary_text(state))


def cmd_topics(args, state):
    if not state["topics"]:
        print("No topics yet.")
        return
    for slug, t in sorted(state["topics"].items(), key=lambda kv: kv[1].get("updated", ""), reverse=True):
        active = "*" if slug == state.get("active_topic") else " "
        nodes = t.get("plan", {}).get("nodes", [])
        done = sum(1 for n in nodes if n.get("status") == "done")
        print(f"{active} {slug:28} {t['status']:9} {t['started']}  {done}/{len(nodes)} nodes  {t['title']}")


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


def cmd_start(args, state):
    slug = args.slug or L.slugify(args.title)
    if slug in state["topics"] and state["topics"][slug]["status"] != "finished":
        state["active_topic"] = slug
        topic = state["topics"][slug]
        state["log_target"] = topic.get("note")
        _touch(topic, "resume", "resumed via start")
        _save(state, f"Topic '{slug}' already exists; made it active (status {topic['status']}).")
        return
    if slug in state["topics"]:
        slug = f"{slug}-{L.today()}"
    previous = state.get("active_topic")
    if previous and previous in state["topics"] and state["topics"][previous]["status"] in ("probing", "planning", "teaching"):
        state["topics"][previous]["status"] = "paused"
        _touch(state["topics"][previous], "pause", f"parked when '{slug}' started; resume with: python3 scripts/state.py resume {previous}")
    note = _new_note(args.title, slug)
    topic = {
        "title": args.title,
        "started": L.today(),
        "updated": L.ts(),
        "finished": None,
        "status": "probing",
        "goal": args.goal or "",
        "note": note,
        "edge": [],
        "plan": {"approved": False, "mermaid": "", "nodes": []},
        "next": "Phase 1: probe the learner's level (quiz) and pin the goal (ask).",
        "log": [],
    }
    _touch(topic, "start", f"topic created, note {L.rel(note)}")
    state["topics"][slug] = topic
    state["active_topic"] = slug
    state["log_target"] = note
    _save(state, f"Started topic '{slug}'. Note: {L.rel(note)}. Status: probing.")


def cmd_goal(args, state):
    slug, topic = _topic(state)
    topic["goal"] = args.text
    _touch(topic, "goal", args.text)
    _save(state, f"Goal recorded for '{slug}'.")


def cmd_edge(args, state):
    slug, topic = _topic(state)
    topic.setdefault("edge", []).append(args.text)
    _touch(topic, "edge", args.text)
    _save(state, f"Edge finding recorded ({len(topic['edge'])} total).")


def cmd_plan_set(args, state):
    slug, topic = _topic(state)
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"error: plan-set expects JSON on stdin: {exc}")
    nodes = []
    for n in data.get("nodes", []):
        if "id" not in n or "label" not in n:
            sys.exit("error: every node needs 'id' and 'label'")
        nodes.append({
            "id": str(n["id"]),
            "label": str(n["label"]),
            "depends": [str(d) for d in n.get("depends", [])],
            "why": n.get("why", ""),
            "status": n.get("status", "pending"),
            "check": n.get("check", ""),
            "summary": n.get("summary", ""),
        })
    topic["plan"] = {"approved": False, "mermaid": data.get("mermaid", ""), "nodes": nodes}
    topic["status"] = "planning"
    topic["next"] = "Present the plan (prose + mermaid map) and wait for the learner's go-ahead."
    _touch(topic, "plan-set", f"{len(nodes)} nodes")
    _save(state, f"Plan recorded with {len(nodes)} nodes (not yet approved).")


def cmd_plan_show(args, state):
    slug, topic = _topic(state)
    nodes = topic.get("plan", {}).get("nodes", [])
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
        done = sum(1 for n in nodes if n.get("status") == "done")
        print(f"\n{done}/{len(nodes)} nodes done. Green = done, orange = shaky, yellow = current. Refer to nodes as `id · label`.")


def cmd_plan_approve(args, state):
    slug, topic = _topic(state)
    topic.setdefault("plan", {})["approved"] = True
    topic["status"] = "teaching"
    nodes = topic["plan"].get("nodes", [])
    first = next((n for n in nodes if n.get("status", "pending") == "pending"), None)
    topic["next"] = f"Teach node {first['id']} ({first['label']}): motivate, establish, connect, check." if first else "Teach the first node."
    _touch(topic, "plan-approve", "learner approved the plan")
    _save(state, f"Plan approved. Status: teaching. Next: {topic['next']}")


def _find_node(topic: dict, node_id: str) -> dict:
    for n in topic.get("plan", {}).get("nodes", []):
        if n["id"] == node_id:
            return n
    sys.exit(f"error: node '{node_id}' not in plan. Known: {[n['id'] for n in topic.get('plan', {}).get('nodes', [])]}")


def cmd_node_add(args, state):
    slug, topic = _topic(state)
    nodes = topic.setdefault("plan", {"approved": False, "mermaid": "", "nodes": []}).setdefault("nodes", [])
    if any(n["id"] == args.id for n in nodes):
        sys.exit(f"error: node '{args.id}' already exists")
    depends = [d.strip() for d in (args.depends or "").split(",") if d.strip()]
    nodes.append({"id": args.id, "label": args.label, "depends": depends, "why": "", "status": "pending", "check": "", "summary": ""})
    _touch(topic, "node-add", f"{args.id} {args.label}")
    _save(state, f"Node '{args.id}' added ({len(nodes)} nodes).")


def cmd_node_done(args, state):
    slug, topic = _topic(state)
    node = _find_node(topic, args.id)
    node["status"] = "done"
    node["summary"] = args.summary
    node["check"] = args.check or node.get("check") or ""
    node["done_at"] = L.ts()
    nodes = topic["plan"]["nodes"]
    nxt = next((n for n in nodes if n.get("status", "pending") == "pending"), None)
    topic["next"] = (
        f"Teach node {nxt['id']} ({nxt['label']}): motivate, establish, connect, check."
        if nxt else "All nodes done: run the exit check (short answers, plus a coding task if applicable), then finish."
    )
    _touch(topic, "node-done", f"{args.id}: {args.summary}")
    _save(state, f"Node '{args.id}' done. Next: {topic['next']}")


def cmd_node_shaky(args, state):
    slug, topic = _topic(state)
    node = _find_node(topic, args.id)
    node["status"] = "shaky"
    node["summary"] = args.why
    topic["next"] = f"Repair node {args.id} ({node['label']}) before building on it: {args.why}"
    _touch(topic, "node-shaky", f"{args.id}: {args.why}")
    _save(state, f"Node '{args.id}' marked shaky. Next: {topic['next']}")


def cmd_next(args, state):
    slug, topic = _topic(state)
    topic["next"] = args.text
    _touch(topic, "next", args.text)
    _save(state, "Next step recorded.")


def cmd_checkpoint(args, state):
    slug, topic = _topic(state)
    _touch(topic, "checkpoint", args.text)
    _save(state, f"Checkpoint saved for '{slug}' at {L.fmt_local(topic['updated'])}.")


def cmd_pause(args, state):
    slug, topic = _topic(state)
    topic["status"] = "paused"
    _touch(topic, "pause", "paused by learner")
    state["active_topic"] = None
    state["log_target"] = None
    _save(state, f"Topic '{slug}' paused. Resume with: python3 scripts/state.py resume {slug}")


def cmd_resume(args, state):
    if args.slug not in state["topics"]:
        sys.exit(f"error: unknown topic '{args.slug}'")
    topic = state["topics"][args.slug]
    if topic["status"] == "finished":
        sys.exit("error: topic is finished; start a new topic or review it with /review")
    if topic["status"] == "paused":
        topic["status"] = "teaching" if topic.get("plan", {}).get("approved") else ("planning" if topic.get("plan", {}).get("nodes") else "probing")
    state["active_topic"] = args.slug
    state["log_target"] = topic.get("note")
    _touch(topic, "resume", "resumed")
    L.append_text(topic["note"], f"\n\n> [!info] Session resumed {L.fmt_local(L.ts())}\n")
    _save(state, f"Resumed '{args.slug}' (status {topic['status']}). Next: {topic.get('next','')}")


def cmd_finish(args, state):
    slug, topic = _topic(state)
    topic["status"] = "finished"
    topic["finished"] = L.today()
    topic["next"] = "Finished. Reviews are scheduled in the deck."
    if args.summary:
        topic["summary"] = args.summary
    _touch(topic, "finish", args.summary or "topic finished")
    if topic.get("note"):
        L.append_text(topic["note"], f"\n\n> [!success] Topic finished {L.fmt_local(L.ts())}\n" + (f"\n{args.summary}\n" if args.summary else ""))
    state["active_topic"] = None
    state["log_target"] = None
    _save(state, f"Topic '{slug}' finished on {topic['finished']}.")


def cmd_log_target(args, state):
    if args.clear:
        state["log_target"] = None
        _save(state, "Session log target cleared.")
        return
    if not args.path:
        sys.exit("error: give a path or --clear")
    path = L.resolve(args.path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\ndate: {L.today()}\ntags: [learning]\n---\n", "utf-8")
    state["log_target"] = str(path)
    _save(state, f"Session log target: {L.rel(path)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show").set_defaults(fn=cmd_show)
    sub.add_parser("topics").set_defaults(fn=cmd_topics)
    p = sub.add_parser("start"); p.add_argument("title"); p.add_argument("--goal"); p.add_argument("--slug"); p.set_defaults(fn=cmd_start)
    p = sub.add_parser("goal"); p.add_argument("text"); p.set_defaults(fn=cmd_goal)
    p = sub.add_parser("edge"); p.add_argument("text"); p.set_defaults(fn=cmd_edge)
    sub.add_parser("plan-set").set_defaults(fn=cmd_plan_set)
    p = sub.add_parser("plan-show"); p.add_argument("node", nargs="?"); p.set_defaults(fn=cmd_plan_show)
    sub.add_parser("plan-approve").set_defaults(fn=cmd_plan_approve)
    p = sub.add_parser("node-add"); p.add_argument("id"); p.add_argument("label"); p.add_argument("--depends"); p.set_defaults(fn=cmd_node_add)
    p = sub.add_parser("node-done"); p.add_argument("id"); p.add_argument("summary"); p.add_argument("--check", choices=["short", "mcq", "code", "none"]); p.set_defaults(fn=cmd_node_done)
    p = sub.add_parser("node-shaky"); p.add_argument("id"); p.add_argument("why"); p.set_defaults(fn=cmd_node_shaky)
    p = sub.add_parser("next"); p.add_argument("text"); p.set_defaults(fn=cmd_next)
    p = sub.add_parser("checkpoint"); p.add_argument("text"); p.set_defaults(fn=cmd_checkpoint)
    sub.add_parser("pause").set_defaults(fn=cmd_pause)
    p = sub.add_parser("resume"); p.add_argument("slug"); p.set_defaults(fn=cmd_resume)
    p = sub.add_parser("finish"); p.add_argument("--summary"); p.set_defaults(fn=cmd_finish)
    p = sub.add_parser("log-target"); p.add_argument("path", nargs="?"); p.add_argument("--clear", action="store_true"); p.set_defaults(fn=cmd_log_target)

    args = parser.parse_args(argv)
    state = L.load_state()
    args.fn(args, state)


if __name__ == "__main__":
    main()
