#!/usr/bin/env python3
"""Spaced repetition deck (SM-2 scheduling) for the learning system.

Cards live in state/deck.json. Every card has a type:
  short  free-text question graded by the teacher against the stored answer
  mcq    multiple choice; options are stored, the answer is one option label
  code   a coding task; `task` points at the exercise folder

Grades are 0-5 (SM-2 quality). The mapping is shared by teaching, review and
code tasks (see docs/SYSTEM.md "Grade semantics"):
  5 complete and precise   4 correct, small gap or hesitation   3 core present, minor point missing
  2 wrong / missing an essential point / needed real help   1 wrong   0 blank or "I don't know"
q >= 3 always means: every required point met AND no substantive assistance.
`grade --assisted` or `--missing-required` caps q at 2 even if the teacher says 4.

Scheduling rules (deck v2):
  - an attempt kind is initial, practice, review, repair or exit
  - a practice or repair success (a reattempt right after an explanation) is history only
  - a success on a day the card already advanced is history only
  - a review before the due date does not advance the schedule (early review)
  - any failure is a lapse: interval 1, due tomorrow, ease down
  - the same --op id applied twice is a no-op
  - days follow the configured timezone; LEARN_NOW=<iso> injects the clock

Usage (from the repo root):
  python3 scripts/srs.py add --topic SLUG --type short --q "..." --a "..." [--points "k1;k2"] [--options "A|B|C"] [--task DIR] [--node ID] [--check ID]
  python3 scripts/srs.py promote < card.json         # {"topic","node","check","type","kind","variants":[...]}
  python3 scripts/srs.py due [--topic SLUG] [--limit N] [--budget MIN] [--all] [--json]
  python3 scripts/srs.py grade ID Q [--kind initial|practice|review|repair|exit] [--op ID] [--assisted] [--missing-required] [--variant V] [--note "..."]
  python3 scripts/srs.py stats [--json]
  python3 scripts/srs.py list [--topic SLUG] [--all]
  python3 scripts/srs.py show ID [--json]
  python3 scripts/srs.py history ID
  python3 scripts/srs.py forecast [--days 14]
  python3 scripts/srs.py suspend ID | unsuspend ID
  python3 scripts/srs.py amend-key ID --reason "..." < key.json        # clarify a key; history stays valid
  python3 scripts/srs.py invalidate-key ID --reason "..." < key.json   # wrong key; old attempts no longer count
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys

import learnlib as L

KINDS = L.ATTEMPT_KINDS


# --- pure scheduling ----------------------------------------------------------

def _clamp_q(q) -> int:
    q = int(q)
    if not 0 <= q <= 5:
        raise L.LearnError("grade must be 0-5")
    return q


def sm2_step(card: dict, q: int) -> None:
    """One SM-2 step that DOES change the schedule (caller decided it should)."""
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
    card.update({"ease": round(ease, 2), "reps": reps, "interval": interval})


def apply_grade(card: dict, q: int, day: str, kind: str = "review", independent: bool = True,
                required_met: bool = True, note: str = "", variant: str = "", op: str | None = None) -> dict:
    """Record one graded attempt on a card and update its schedule per the rules
    in the module docstring. Returns a small outcome dict for the caller to print."""
    if kind not in KINDS:
        raise L.LearnError(f"kind must be one of {KINDS}")
    q = _clamp_q(q)
    capped = ""
    if q >= 3 and not independent:
        q, capped = 2, "assisted: not independent recall"
    elif q >= 3 and not required_met:
        q, capped = 2, "missing a required point"
    if variant and variant not in {v.get("id") for v in card.get("variants", [])} and variant != "v1":
        raise L.LearnError(f"card {card['id']} has no variant {variant!r}")
    entry = {"date": day, "q": q, "note": note or "", "kind": kind, "variant": variant or "v1",
             "rubric_version": int(card.get("rubric_version", 1)), "valid": True}
    if op:
        entry["op"] = op
    if capped:
        entry["capped"] = capped
    scheduled = False
    reason = ""
    if q >= 3:
        if kind in ("practice", "repair"):
            reason = f"{kind} attempt: history only, schedule unchanged"
        elif card.get("last_graduated") == day:
            reason = "already advanced today: history only"
        elif kind == "review" and int(card.get("reps", 0)) > 0 and card.get("due", day) > day:
            reason = f"early review (due {card['due']}): schedule unchanged"
            entry["early"] = True
        else:
            sm2_step(card, q)
            card["due"] = L.date_add(day, int(card["interval"]))
            card["last_graduated"] = day
            scheduled = True
            reason = f"advanced: interval {card['interval']}d"
    else:
        sm2_step(card, q)
        card["due"] = L.date_add(day, 1)
        scheduled = True
        reason = "lapse: due tomorrow"
    card.setdefault("history", []).append(entry)
    card.setdefault("asked", []).append({"date": day, "variant": entry["variant"]})
    if len(card["asked"]) > 50:
        card["asked"] = card["asked"][-50:]
    return {"q": q, "capped": capped, "scheduled": scheduled, "reason": reason, "due": card["due"],
            "interval": card.get("interval"), "ease": card.get("ease")}


def recompute_from_history(card: dict) -> None:
    """Rebuild the schedule from the valid history entries only (after a key was invalidated)."""
    entries = [h for h in card.get("history", []) if h.get("valid", True)]
    card.update({"ease": 2.5, "reps": 0, "interval": 1, "lapses": 0, "last_graduated": None,
                 "due": L.date_add(card.get("created", L.today()), 1)})
    for h in entries:
        q = int(h.get("q", 0))
        kind = h.get("kind", "review")
        day = h["date"]
        if q >= 3:
            if kind in ("practice", "repair") or card.get("last_graduated") == day or h.get("early"):
                continue
            sm2_step(card, q)
            card["due"] = L.date_add(day, int(card["interval"]))
            card["last_graduated"] = day
        else:
            sm2_step(card, q)
            card["due"] = L.date_add(day, 1)
    if card["due"] < L.today() and not entries:
        card["due"] = L.date_add(L.today(), 1)


def _snapshot_key(card: dict) -> dict:
    return {k: json.loads(json.dumps(card.get(k))) for k in ("question", "answer", "key_points", "options", "explanation", "variants", "rubric_version")}


def _apply_new_key(card: dict, new: dict) -> None:
    for k in ("question", "answer", "explanation"):
        if k in new:
            card[k] = str(new[k]).strip()
    if "key_points" in new:
        card["key_points"] = [str(p).strip() for p in new["key_points"] if str(p).strip()]
    if "options" in new:
        card["options"] = [str(o).strip() for o in new["options"] if str(o).strip()]
    if "variants" in new:
        card["variants"] = new["variants"]
    L.validate_card(card)


def amend_key(card: dict, new: dict, reason: str, day: str) -> None:
    """Clarify or extend a key. Earlier attempts remain valid evidence."""
    snap = _snapshot_key(card)
    snap.update({"replaced": day, "reason": reason, "mode": "amend"})
    card.setdefault("key_history", []).append(snap)
    _apply_new_key(card, new)
    card["rubric_version"] = int(card.get("rubric_version", 1)) + 1


def invalidate_key(card: dict, new: dict, reason: str, day: str) -> int:
    """The old key was wrong or ambiguous: keep the old key and every attempt, but
    those attempts no longer count as evidence about the learner. Returns the
    number of attempts excluded."""
    snap = _snapshot_key(card)
    snap.update({"replaced": day, "reason": reason, "mode": "invalidate"})
    card.setdefault("key_history", []).append(snap)
    old_version = int(card.get("rubric_version", 1))
    excluded = 0
    for h in card.get("history", []):
        if int(h.get("rubric_version", 1)) <= old_version and h.get("valid", True):
            h["valid"] = False
            h["invalid_reason"] = f"key v{old_version} invalidated: {reason}"
            excluded += 1
    _apply_new_key(card, new)
    card["rubric_version"] = old_version + 1
    recompute_from_history(card)
    card["needs_replacement_check"] = True
    return excluded


# --- selection -----------------------------------------------------------------

def is_due(card: dict, on: str) -> bool:
    return not card.get("suspended") and card["due"] <= on


def estimate_minutes(card: dict) -> float:
    costs = L.config().get("reviewCostMinutes", {})
    return float(costs.get(card["type"], 2.5))


def select_due(cards: list[dict], on: str, budget: float | None, limit: int | None, topic: str | None = None):
    """Overdue-first selection within a time budget. Returns (selected, deferred, minutes).
    Code cards are deferred to the 'offer if time' list unless they fit after the rest."""
    due = [c for c in cards if is_due(c, on) and (not topic or c["topic"] == topic)]
    due.sort(key=lambda c: (c["due"], c["created"], c["id"]))
    selected: list[dict] = []
    deferred: list[dict] = []
    minutes = 0.0
    for c in [c for c in due if c["type"] != "code"] + [c for c in due if c["type"] == "code"]:
        cost = estimate_minutes(c)
        if limit is not None and len(selected) >= limit:
            deferred.append(c)
            continue
        if budget is not None and selected and minutes + cost > budget:
            deferred.append(c)
            continue
        selected.append(c)
        minutes += cost
    return selected, deferred, minutes


def pick_variant(card: dict) -> dict:
    """The variant asked least recently (never asked first). The primary variant is 'v1'."""
    variants = card.get("variants") or []
    if not variants:
        return {"id": "v1", "question": card["question"], "answer": card["answer"],
                "key_points": card.get("key_points", []), "options": card.get("options", []), "code": card.get("code", "")}
    last_asked: dict[str, str] = {}
    for a in card.get("asked", []):
        last_asked[a.get("variant", "v1")] = a.get("date", "")
    return min(variants, key=lambda v: (last_asked.get(v["id"], ""), v["id"]))


def card_from_check(topic: str, node: str, check: dict, existing_ids=()) -> dict:
    """Build a card from a prepared check (all its variants travel with the card)."""
    variants = []
    for v in check["variants"]:
        variants.append({"id": v["id"], "question": v["question"], "code": v.get("code", ""), "answer": v["answer"],
                         "key_points": list(v.get("required", [])), "accepted": list(v.get("accepted", [])),
                         "options": list(v.get("options", [])), "rubric_version": int(v.get("rubric_version", 1))})
    first = variants[0]
    card = {
        "id": L.new_id("c", existing_ids), "topic": topic, "node": node, "check": check_key(node, check["id"]), "type": check["type"],
        "kind": check.get("kind", "concept"), "question": first["question"], "code": first.get("code", ""),
        "answer": first["answer"], "key_points": first["key_points"], "options": first["options"],
        "explanation": check.get("explanation", ""), "task": check.get("exercise", ""), "variants": variants, "asked": [],
        "created": L.today(), "due": L.date_add(L.today(), 1), "interval": 1, "ease": 2.5, "reps": 0, "lapses": 0,
        "history": [], "suspended": False, "rubric_version": max(int(v["rubric_version"]) for v in variants),
        "key_history": [], "last_graduated": None,
    }
    L.validate_card(card)
    return card


def find(deck: dict, cid: str) -> dict:
    for card in deck["cards"]:
        if card["id"] == cid:
            return card
    raise L.LearnError(f"no card '{cid}'")


def check_key(node: str, check_id: str) -> str:
    """Cards store the check as 'node/check' because check ids repeat across nodes (q1, q2 ...)."""
    return f"{node}/{check_id}" if node and "/" not in check_id else check_id


def find_by_check(deck: dict, topic: str, node: str, check_id: str) -> dict | None:
    key = check_key(node, check_id)
    for card in deck["cards"]:
        if card.get("topic") == topic and card.get("node") == node and card.get("check") == key:
            return card
    return None


# --- formatting --------------------------------------------------------------------

def fmt_card(card: dict, full: bool = False) -> str:
    head = (f"{card['id']}  [{card['type']}] {card['topic']}  due {card['due']}  ease {card.get('ease', 2.5)}  "
            f"reps {card.get('reps', 0)}  key v{card.get('rubric_version', 1)}")
    if card.get("needs_replacement_check"):
        head += "  (key replaced: needs a fresh check)"
    if not full:
        q = card["question"].strip().splitlines()[0]
        return head + "\n    Q: " + (q[:110] + ("…" if len(q) > 110 else ""))
    lines = [head, "Q: " + card["question"]]
    if card.get("code"):
        lines.append("Code:\n" + card["code"])
    if card.get("options"):
        lines.append("Options: " + " | ".join(card["options"]))
    lines.append("A: " + card["answer"])
    if card.get("key_points"):
        lines.append("Required points: " + "; ".join(card["key_points"]))
    if card.get("explanation"):
        lines.append("Explanation: " + card["explanation"])
    if card.get("task"):
        lines.append("Task: " + card["task"])
    if card.get("node"):
        lines.append("Node: " + card["node"] + (f" · check {card['check']}" if card.get("check") else ""))
    if len(card.get("variants", [])) > 1:
        lines.append("Variants: " + ", ".join(v["id"] for v in card["variants"]) + f" (next: {pick_variant(card)['id']})")
    if card.get("history"):
        lines.append("History: " + ", ".join(
            f"{h['date']}={h['q']}{'' if h.get('valid', True) else '(invalid key)'}{'(' + h['kind'][0] + ')' if h.get('kind') else ''}"
            for h in card["history"][-8:]))
    return "\n".join(lines)


def fmt_variant_for_chat(card: dict, variant: dict) -> str:
    """Question text ready to paste: code as a fenced block, options lettered, 'I don't know' last."""
    out = [variant["question"].strip()]
    if variant.get("code"):
        out.append("```c\n" + variant["code"].rstrip() + "\n```")
    if card["type"] == "mcq":
        opts = [o for o in variant.get("options", []) if o.lower() != "i don't know"]
        random.shuffle(opts)
        opts.append("I don't know")
        out.append("\n".join(f"{chr(65 + i)}) {o}" for i, o in enumerate(opts)))
    return "\n\n".join(out)


# --- commands ----------------------------------------------------------------

def _read_stdin_json() -> dict:
    raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise L.LearnError(f"expected JSON on stdin: {exc}")


def cmd_add(args):
    with L.Store(write=True) as st:
        deck = st.deck
        card = {
            "id": L.new_id("c", {c["id"] for c in deck["cards"]}),
            "topic": args.topic, "node": args.node or "", "check": args.check or "", "type": args.type, "kind": args.kind,
            "question": args.q.strip(), "code": "", "answer": args.a.strip(),
            "key_points": [p.strip() for p in (args.points or "").split(";") if p.strip()],
            "options": [o.strip() for o in (args.options or "").split("|") if o.strip()],
            "explanation": "", "task": args.task or "", "variants": [], "asked": [],
            "created": L.today(), "due": args.due or L.date_add(L.today(), 1),
            "interval": 1, "ease": 2.5, "reps": 0, "lapses": 0, "history": [], "suspended": False,
            "rubric_version": 1, "key_history": [], "last_graduated": None,
        }
        L.validate_card(card)
        if card["type"] == "code" and not card["task"]:
            print("warning: code card without --task path", file=sys.stderr)
        deck["cards"].append(card)
        st.commit()
        print(card["id"])


def cmd_promote(args):
    data = _read_stdin_json()
    for field in ("topic", "node", "check"):
        if not data.get(field):
            raise L.LearnError(f"promote needs {field}")
    check = {"id": data["check"], "type": data.get("type", "short"), "kind": data.get("kind", "concept"),
             "variants": data.get("variants", []), "explanation": data.get("explanation", ""), "exercise": data.get("exercise", "")}
    L.validate_check(check, "promote")
    with L.Store(write=True) as st:
        if st.already_applied(args.op):
            print(f"op {args.op} already applied; nothing changed")
            return
        existing = find_by_check(st.deck, data["topic"], data["node"], data["check"])
        if existing:
            print(f"{existing['id']} (already promoted)")
            return
        card = card_from_check(data["topic"], data["node"], check, {c["id"] for c in st.deck["cards"]})
        st.deck["cards"].append(card)
        st.commit(op_id=args.op)
        print(card["id"])


def cmd_due(args):
    on = L.today()
    deck = L.load_deck()
    budget = None if args.all else (args.budget if args.budget is not None else float(L.config().get("reviewMinutes", 10)))
    selected, deferred, minutes = select_due(deck["cards"], on, budget, args.limit, args.topic)
    if args.json:
        out = []
        for c in selected:
            v = pick_variant(c)
            item = dict(c)
            item["ask_variant"] = v["id"]
            item["ask_text"] = fmt_variant_for_chat(c, v)
            out.append(item)
        print(json.dumps({"date": on, "selected": out, "deferred": [c["id"] for c in deferred],
                          "minutes": round(minutes, 1), "budget": budget}, indent=2, ensure_ascii=False))
        return
    if not selected:
        print(f"No cards due on {on}.")
        return
    total = len(selected) + len(deferred)
    print(f"{total} card(s) due on {on}; {len(selected)} selected (~{minutes:.0f} min"
          + (f" of a {budget:.0f} min budget" if budget is not None else "") + ")"
          + (f"; {len(deferred)} deferred, due dates unchanged" if deferred else "") + ":")
    for card in selected:
        v = pick_variant(card)
        print(fmt_card(card, full=True))
        if v["id"] != "v1" or card.get("variants"):
            print(f"Ask variant {v['id']}:\n{fmt_variant_for_chat(card, v)}")
        print()
    if deferred:
        print("Deferred: " + ", ".join(f"{c['id']} ({c['type']}, due {c['due']})" for c in deferred))


def cmd_grade(args):
    with L.Store(write=True) as st:
        if st.already_applied(args.op):
            print(f"op {args.op} already applied; nothing changed")
            return
        card = find(st.deck, args.id)
        outcome = apply_grade(card, int(args.q), L.today(), kind=args.kind, independent=not args.assisted,
                              required_met=not args.missing_required, note=args.note or "", variant=args.variant or "",
                              op=args.op)
        card.pop("needs_replacement_check", None) if args.kind in ("initial", "review", "exit") else None
        st.commit(op_id=args.op)
        cap = f" (capped from {args.q}: {outcome['capped']})" if outcome["capped"] else ""
        print(f"{card['id']} graded {outcome['q']}{cap} [{args.kind}]: {outcome['reason']}; next due {outcome['due']} "
              f"(interval {outcome['interval']}d, ease {outcome['ease']})")


def cmd_stats(args):
    on = L.today()
    deck = L.load_deck()
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
    selected, deferred, minutes = select_due(cards, on, float(L.config().get("reviewMinutes", 10)), None)
    data = {
        "date": on, "total": len(cards), "new": sum(1 for c in cards if c.get("reps", 0) == 0),
        "due_today": len(due_today), "due_tomorrow": len(due_tomorrow), "due_next_7_days": len(due_week),
        "due_by_topic": per_topic, "last_review": last,
        "by_type": {t: sum(1 for c in cards if c["type"] == t) for t in ("short", "mcq", "code")},
        "session_minutes": round(minutes, 1), "session_cards": len(selected), "deferred": len(deferred),
        "needs_replacement_check": sum(1 for c in cards if c.get("needs_replacement_check")),
    }
    if args.json:
        print(json.dumps(data, indent=2))
        return
    print(f"Deck on {on}: {data['total']} cards ({data['new']} never reviewed) · "
          f"due today {data['due_today']} · tomorrow +{data['due_tomorrow']} · next 7 days {data['due_next_7_days']}")
    if per_topic:
        print("Due by topic: " + ", ".join(f"{k} {v}" for k, v in sorted(per_topic.items())))
    print("By type: " + ", ".join(f"{k} {v}" for k, v in data["by_type"].items()) + (f" · last review {last}" if last else ""))
    if data["due_today"]:
        print(f"A default session takes {data['session_cards']} of them (~{data['session_minutes']:.0f} min); {data['deferred']} deferred.")


def cmd_list(args):
    deck = L.load_deck()
    cards = [c for c in deck["cards"] if (args.all or not c.get("suspended")) and (not args.topic or c["topic"] == args.topic)]
    cards.sort(key=lambda c: (c["due"], c["topic"]))
    if not cards:
        print("No cards.")
    for card in cards:
        print(fmt_card(card))


def cmd_show(args):
    card = find(L.load_deck(), args.id)
    if args.json:
        print(json.dumps(card, indent=2, ensure_ascii=False))
        return
    print(fmt_card(card, full=True))


def cmd_history(args):
    card = find(L.load_deck(), args.id)
    print(f"{card['id']} [{card['type']}] key v{card.get('rubric_version', 1)} · ease {card.get('ease')} reps {card.get('reps')} due {card['due']}")
    for h in card.get("history", []):
        flag = "" if h.get("valid", True) else " INVALID(" + h.get("invalid_reason", "") + ")"
        extra = " early" if h.get("early") else ""
        cap = f" capped[{h['capped']}]" if h.get("capped") else ""
        print(f"  {h['date']}  q={h['q']}  {h.get('kind', '?'):8} v{h.get('rubric_version', 1)} {h.get('variant', 'v1')}{extra}{cap}{flag}  {h.get('note', '')}")
    for k in card.get("key_history", []):
        print(f"  key v{k.get('rubric_version')} {k.get('mode')}d {k.get('replaced')}: {k.get('reason')}")


def cmd_forecast(args):
    on = dt.date.fromisoformat(L.today())
    counts: dict[str, int] = {}
    for c in L.load_deck()["cards"]:
        if c.get("suspended"):
            continue
        due = max(dt.date.fromisoformat(c["due"]), on)
        counts[due.isoformat()] = counts.get(due.isoformat(), 0) + 1
    for i in range(args.days):
        day = (on + dt.timedelta(days=i)).isoformat()
        n = counts.get(day, 0)
        print(f"{day}  {'#' * min(n, 40)}{' ' if n else ''}{n}")


def cmd_suspend(args, value=True):
    with L.Store(write=True) as st:
        card = find(st.deck, args.id)
        card["suspended"] = value
        st.commit()
        print(f"{card['id']} {'suspended' if value else 'active'}")


def cmd_amend_key(args):
    new = _read_stdin_json()
    with L.Store(write=True) as st:
        card = find(st.deck, args.id)
        amend_key(card, new, args.reason, L.today())
        st.commit()
        print(f"{card['id']} key amended to v{card['rubric_version']}; {len(card.get('history', []))} attempt(s) remain valid evidence")


def cmd_invalidate_key(args):
    new = _read_stdin_json()
    with L.Store(write=True) as st:
        card = find(st.deck, args.id)
        excluded = invalidate_key(card, new, args.reason, L.today())
        st.commit()
        print(f"{card['id']} key invalidated -> v{card['rubric_version']}; {excluded} earlier attempt(s) kept but no longer count; "
              f"schedule reset (due {card['due']}); a replacement check is flagged")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("--topic", required=True); p.add_argument("--type", required=True, choices=list(L.CHECK_TYPES))
    p.add_argument("--q", required=True); p.add_argument("--a", required=True)
    p.add_argument("--points"); p.add_argument("--options"); p.add_argument("--task"); p.add_argument("--node"); p.add_argument("--due")
    p.add_argument("--check"); p.add_argument("--kind", default="concept", choices=["concept", "misconception", "procedure", "task"])
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("promote"); p.add_argument("--op"); p.set_defaults(fn=cmd_promote)
    p = sub.add_parser("due"); p.add_argument("--topic"); p.add_argument("--limit", type=int); p.add_argument("--budget", type=float)
    p.add_argument("--all", action="store_true"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_due)
    p = sub.add_parser("grade"); p.add_argument("id"); p.add_argument("q"); p.add_argument("--note")
    p.add_argument("--kind", default="review", choices=list(KINDS)); p.add_argument("--op")
    p.add_argument("--assisted", action="store_true"); p.add_argument("--missing-required", action="store_true"); p.add_argument("--variant")
    p.set_defaults(fn=cmd_grade)
    p = sub.add_parser("stats"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_stats)
    p = sub.add_parser("list"); p.add_argument("--topic"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("id"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("history"); p.add_argument("id"); p.set_defaults(fn=cmd_history)
    p = sub.add_parser("forecast"); p.add_argument("--days", type=int, default=14); p.set_defaults(fn=cmd_forecast)
    p = sub.add_parser("suspend"); p.add_argument("id"); p.set_defaults(fn=lambda a: cmd_suspend(a, True))
    p = sub.add_parser("unsuspend"); p.add_argument("id"); p.set_defaults(fn=lambda a: cmd_suspend(a, False))
    p = sub.add_parser("amend-key"); p.add_argument("id"); p.add_argument("--reason", required=True); p.set_defaults(fn=cmd_amend_key)
    p = sub.add_parser("invalidate-key"); p.add_argument("id"); p.add_argument("--reason", required=True); p.set_defaults(fn=cmd_invalidate_key)
    args = parser.parse_args(argv)
    L.cli_main(lambda: args.fn(args))


if __name__ == "__main__":
    main()
