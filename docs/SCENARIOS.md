# Teaching scenarios: expected tool calls per turn

These are static scenario checks against the prepared OpenMP material, run on 2026-09-25 with the
scripts (not a live Claude session; see "What was measured" at the end). Each scenario lists the
turn, the tool calls the teach skill prescribes, and what the scripts printed. Learner-facing text
contains no bookkeeping.

## 1. Quick question (no lesson ceremony)

Learner: "Quick one: why does `nowait` need `schedule(static)` to be safe between two loops?"

Expected tool calls: **0** (answer from established knowledge; the fact is in the prep for n9).
If the claim were uncertain: one `researcher` call, then the answer, then `prep-node` to persist it.

Observed: the answer is written directly. No `start`, no probe, no card.

## 2. Ordinary explanation of a prepared node

Learner: "continue" (NEXT says: Teach n7 · Synchronization (prepared)).

Expected tool calls: `state.py prep-show n7` (read), then the teaching message, then `state.py ask n7`
(prints the question; pasted as printed), end of turn. **2 calls**, no research, no subagent, no
diagram, no map.

Observed `ask n7` output (teacher line + question):

```
[p… · n7 · q1/v1 · short · initial · key v1]

Answer (a), (b) and (c) for this region.

```c
int total = 0;
#pragma omp parallel num_threads(4)
{
    int mine = work(omp_get_thread_num());
    #pragma omp critical
    total += mine;
}
printf("%d\n", total);
```
```

## 3. Correct response

Learner answers (a) critical orders the two updates so they never overlap, printf is after the
region's barrier; (b) atomic on `total += mine`; (c) two coupled updates, needs critical.

Expected tool calls: **1**: `state.py record` with
`{"result":"pass","quality":5}`. It records the attempt, sets n7 readiness `ready`, creates and
grades the review card (q1 is `review: true`), sets NEXT and prints the next node's objective.

Observed output (teacher-only):

```
a…: n7 q1/v1 pass, quality 5, help none
n7 readiness -> ready (independent pass on q1/v1)
card c… created graded 5: advanced: interval 1d; due 2026-09-26
NEXT: Teach n8 · Reductions (prepared; python3 scripts/state.py prep-show n8)
Next node n8 · Reductions: …
  objective: Explain what reduction(op:x) does …
  checks: q1 (short), q2 (short), q3 (mcq), q4 (code)
```

Learner-facing feedback: two or three sentences on what was right and the one precision worth
adding (unnamed criticals share one lock). No mention of cards or readiness.

## 4. Wrong response

Learner answers n8's q1: "reduction(+:s); the copies start at 10; prints 18" (right pragma and
result, wrong idea about the private copies: misconception m1).

Expected tool calls: **1** `state.py record` with
`{"result":"partial","required_missed":["private copies start at the identity 0"],"misconception":"m1"}`.

Observed output (teacher-only):

```
a…: n8 q1/v1 partial, quality 2, help none
n8 readiness -> needs_repair (m1)
card c… created graded 2: lapse: due tomorrow; due 2026-09-26
NEXT: Repair n8: m1
```

The teacher gives the prepared repair for m1 (if the copies started at 10, four threads would
contribute 10 each: 58, not 18) and re-checks with the fresh variant:
`state.py ask n8 --check q1 --kind repair` (**1 call**, variant v2 is chosen automatically), then
`record` on the reply:

```
a…: n8 q1/v2 pass, quality 4, help none
n8 readiness -> ready (independent pass on q1/v2)
card c… graded 4: repair attempt: history only, schedule unchanged; due 2026-09-26
NEXT: Teach n9 · Scheduling: static, dynamic, guided, chunk size (prepared; …)
```

The repair pass restores readiness (the answer was independent) but does not advance the card's
schedule: the first real retrieval is still tomorrow. No new planning ceremony, no research, no map.

## 5. Continuation after compaction or restart

SessionStart hook injects the snapshot (about 12 lines), including
`PENDING p… · short · n7 q1/v1 · answer recorded, NOT yet graded (run record)`.

Expected tool calls: `state.py pending` (**1 call**), which prints the same question, the recorded
answer and the grading key; then `record`. No re-probing, no re-teaching, no transcript reading.

## 6. Follow-up outside the prepared material

Learner: "Does `#pragma omp atomic` imply a flush on gcc 13?"

Expected: answer from the verified n7 claim c5 (relaxed default, strong flush of x's location)
with **0 calls**. If the question goes beyond the registry (say, gcc's code generation on ARM),
**1** narrow `researcher` call, then the answer, then one `state.py prep-node` (or `correction`) so
the verified result is kept for the next time.

## Baseline for comparison (v1 workflow)

The v1 teach skill required per node: `plan-show n7` (map pasted every node), a researcher call
whenever unsure (no persisted material), `srs.py add` before every short-answer question,
`srs.py grade` after, `state.py node-done` or `node-shaky`, and a free-text `checkpoint`/`next`:
typically **5-6 calls per node** and a re-derived question and key each time. The v2 loop is
**2 calls to pose** (`prep-show`, `ask`) and **1 call to grade** (`record`), with the question and key
resolved from files.

## What was measured

- The command outputs above were produced by running the scripts against the prepared OpenMP
  material in a temporary copy of the state (`LEARN_NOW` fixed to 2026-09-25).
- The number of tool calls per scenario is what the skill instructions prescribe and what the
  scripts make sufficient; it was not measured in a live Claude Code session in this work. A live
  run should be checked against this table the first time the new workflow is used.
