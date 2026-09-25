#!/usr/bin/env python3
"""Spaced repetition deck (SM-2 scheduling) for the learning system.

Cards live in state/deck.json. Every card has a type:
  short  free-text question graded by the teacher against the stored answer
  mcq    multiple choice; options are stored, the answer is one option label
  code   a coding task; `task` points at the exercise folder

Grades are 0-5 (SM-2 quality):
  5 perfect recall     4 correct after a moment      3 correct with difficulty
  2 wrong, but recognised the answer    1 wrong    0 blank / "I don't know"

Usage (from the repo root):
  python scripts/srs.py add --topic SLUG --type short --q "..." --a "..." [--points "k1;k2"] [--options "A|B|C"] [--task DIR] [--node ID]
  python scripts/srs.py due [--topic SLUG] [--limit N] [--json]
  python scripts/srs.py grade ID Q [--note "..."]
  python scripts/srs.py stats [--json]
  python scripts/srs.py list [--topic SLUG] [--all]
  python scripts/srs.py show ID
  python scripts/srs.py forecast [--days 14]
  python scripts/srs.py suspend ID | unsuspend ID
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import string
import sys

import learnlib as L

DECK_DEFAULT = {"version": 1, "cards": []}


def load_deck() -> dict:
    deck = L.read_json(L.deck_path(), None)
    if not isinstance(deck, dict):
        deck = {}
    for key, value in DECK_DEFAULT.items():
        deck.setdefault(key, json.loads(json.dumps(value)))
    return deck


def save_deck(deck: dict) -> None:
    L.write_json(L.deck_path(), deck)


def new_id(deck: dict) -> str:
    existing = {c["id"] for c in deck["cards"]}
    while True:
        cid = "c" + "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
        if cid not in existing:
            return cid


def find(deck: dict, cid: str) -> dict:
    for card in deck["cards"]:
        if card["id"] == cid:
            return card
    sys.exit(f"error: no card '{cid}'")


def is_due(card: dict, on: str) -> bool:
    return not card.get("suspended") and card["due"] <= on


def sm2(card: dict, q: int) -> None:
    """Apply one SM-2 review with quality q (0-5)."""
    ease = float(card.get("ease", 2.5))
    reps = int(card.get("reps", 0))
    interval = int(card.get("interval", 0))
    if q < 3:
        reps = 0
        interval = 1
        card["lapses"] = int(card.get("lapses", 0)) + 1
    else:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            interval = max(1, round(interval * ease))
    ease = max(1.3, ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    card.update({"ease": round(ease, 2), "reps": reps, "interval": interval, "due": L.date_add(L.today(), interval)})


def fmt_card(card: dict, full: bool = False) -> str:
    head = f"{card['id']}  [{card['type']}] {card['topic']}  due {card['due']}  ease {card.get('ease', 2.5)}  reps {card.get('reps', 0)}"
    if not full:
        q = card["question"].strip().splitlines()[0]
        return head + "\n    Q: " + (q[:110] + ("…" if len(q) > 110 else ""))
    lines = [head, "Q: " + card["question"]]
    if card.get("options"):
        lines.append("Options: " + " | ".join(card["options"]))
    lines.append("A: " + card["answer"])
    if card.get("key_points"):
        lines.append("Key points: " + "; ".join(card["key_points"]))
    if card.get("task"):
        lines.append("Task: " + card["task"])
    if card.get("node"):
        lines.append("Node: " + card["node"])
    if card.get("history"):
        lines.append("History: " + ", ".join(f"{h['date']}={h['q']}" for h in card["history"][-8:]))
    return "\n".join(lines)


# --- commands ----------------------------------------------------------------

def cmd_add(args, deck):
    card = {
        "id": new_id(deck),
        "topic": args.topic,
        "node": args.node or "",
        "type": args.type,
        "question": args.q.strip(),
        "answer": args.a.strip(),
        "key_points": [p.strip() for p in (args.points or "").split(";") if p.strip()],
        "options": [o.strip() for o in (args.options or "").split("|") if o.strip()],
        "task": args.task or "",
        "created": L.today(),
        "due": args.due or L.date_add(L.today(), 1),
        "interval": 1,
        "ease": 2.5,
        "reps": 0,
        "lapses": 0,
        "history": [],
        "suspended": False,
    }
    if card["type"] == "mcq" and card["options"] and card["answer"] not in card["options"]:
        sys.exit("error: for mcq the answer must equal one of the options exactly")
    if card["type"] == "code" and not card["task"]:
        print("warning: code card without --task path", file=sys.stderr)
    deck["cards"].append(card)
    save_deck(deck)
    print(card["id"])


def cmd_due(args, deck):
    on = L.today()
    cards = [c for c in deck["cards"] if is_due(c, on) and (not args.topic or c["topic"] == args.topic)]
    cards.sort(key=lambda c: (c["due"], c["created"]))
    if args.limit:
        cards = cards[: args.limit]
    if args.json:
        print(json.dumps(cards, indent=2, ensure_ascii=False))
        return
    if not cards:
        print(f"No cards due on {on}.")
        return
    print(f"{len(cards)} card(s) due on {on}:")
    for card in cards:
        print(fmt_card(card, full=True))
        print()


def cmd_grade(args, deck):
    card = find(deck, args.id)
    q = int(args.q)
    if not 0 <= q <= 5:
        sys.exit("error: grade must be 0-5")
    sm2(card, q)
    card.setdefault("history", []).append({"date": L.today(), "q": q, "note": args.note or ""})
    save_deck(deck)
    print(f"{card['id']} graded {q}: next due {card['due']} (interval {card['interval']}d, ease {card['ease']})")


def cmd_stats(args, deck):
    on = L.today()
    cards = [c for c in deck["cards"] if not c.get("suspended")]
    due_today = [c for c in cards if c["due"] <= on]
    tomorrow = L.date_add(on, 1)
    week = L.date_add(on, 7)
    due_tomorrow = [c for c in cards if on < c["due"] <= tomorrow]
    due_week = [c for c in cards if on < c["due"] <= week]
    per_topic: dict[str, int] = {}
    for c in due_today:
        per_topic[c["topic"]] = per_topic.get(c["topic"], 0) + 1
    last = max((h["date"] for c in cards for h in c.get("history", [])), default=None)
    data = {
        "date": on,
        "total": len(cards),
        "new": sum(1 for c in cards if c.get("reps", 0) == 0),
        "due_today": len(due_today),
        "due_tomorrow": len(due_tomorrow),
        "due_next_7_days": len(due_week),
        "due_by_topic": per_topic,
        "last_review": last,
        "by_type": {t: sum(1 for c in cards if c["type"] == t) for t in ("short", "mcq", "code")},
    }
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print(f"Deck on {on}: {data['total']} cards ({data['new']} never reviewed) · "
          f"due today {data['due_today']} · tomorrow +{data['due_tomorrow']} · next 7 days {data['due_next_7_days']}")
    if per_topic:
        print("Due by topic: " + ", ".join(f"{k} {v}" for k, v in sorted(per_topic.items())))
    print("By type: " + ", ".join(f"{k} {v}" for k, v in data["by_type"].items()) + (f" · last review {last}" if last else ""))


def cmd_list(args, deck):
    cards = [c for c in deck["cards"] if (args.all or not c.get("suspended")) and (not args.topic or c["topic"] == args.topic)]
    cards.sort(key=lambda c: (c["due"], c["topic"]))
    if not cards:
        print("No cards.")
    for card in cards:
        print(fmt_card(card))


def cmd_show(args, deck):
    print(fmt_card(find(deck, args.id), full=True))


def cmd_forecast(args, deck):
    on = dt.date.fromisoformat(L.today())
    counts: dict[str, int] = {}
    for c in deck["cards"]:
        if c.get("suspended"):
            continue
        due = max(dt.date.fromisoformat(c["due"]), on)
        counts[due.isoformat()] = counts.get(due.isoformat(), 0) + 1
    for i in range(args.days):
        day = (on + dt.timedelta(days=i)).isoformat()
        n = counts.get(day, 0)
        print(f"{day}  {'#' * min(n, 40)}{' ' if n else ''}{n}")


def cmd_suspend(args, deck, value=True):
    card = find(deck, args.id)
    card["suspended"] = value
    save_deck(deck)
    print(f"{card['id']} {'suspended' if value else 'active'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--topic", required=True); p.add_argument("--type", required=True, choices=["short", "mcq", "code"])
    p.add_argument("--q", required=True); p.add_argument("--a", required=True)
    p.add_argument("--points"); p.add_argument("--options"); p.add_argument("--task"); p.add_argument("--node"); p.add_argument("--due")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("due"); p.add_argument("--topic"); p.add_argument("--limit", type=int); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_due)
    p = sub.add_parser("grade"); p.add_argument("id"); p.add_argument("q"); p.add_argument("--note"); p.set_defaults(fn=cmd_grade)
    p = sub.add_parser("stats"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("list"); p.add_argument("--topic"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("forecast"); p.add_argument("--days", type=int, default=14); p.set_defaults(fn=cmd_forecast)
    p = sub.add_parser("suspend"); p.add_argument("id"); p.set_defaults(fn=lambda a, d: cmd_suspend(a, d, True))
    p = sub.add_parser("unsuspend"); p.add_argument("id"); p.set_defaults(fn=lambda a, d: cmd_suspend(a, d, False))
    args = parser.parse_args(argv)
    args.fn(args, load_deck())


if __name__ == "__main__":
    main()
