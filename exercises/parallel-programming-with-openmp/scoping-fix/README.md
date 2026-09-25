---
title: "Fix the data scoping"
date: 2026-09-25
topic: parallel-programming-with-openmp
lang: other
status: done
---
# Fix the data scoping

_Created 2026-09-25 · topic `parallel-programming-with-openmp` · language other_

## Task

Node: **n6 · Data scoping**.

`solution.c` contains two functions. Each has a parallel construct marked `default(none)` and nothing else, so right now it does not even compile. Your job is to **add the data-scoping clauses to the two `#pragma` lines** so that both functions compile, are race-free and give the results described in their comments.

Rules:

- Only edit the two `#pragma` lines. Don't move, add or remove declarations. The point is to fix scoping with clauses, not with the inside/outside rule.
- Scope every variable deliberately: pick the clause that says exactly what is needed, not just one that happens to work.
- The two functions each need a different privatizing clause, and one of them needs two.

## Examples

```
scale_all:   a = {0, 1, 2, 3}, n = 4, scale = 2.0
             -> b = {1, 3, 5, 7},  *last_out = 7
mark_slots:  base = 10  -> slots[10..13] = 1, every other slot 0
             base = 0   -> slots[0..3]   = 1
```

## How to work

1. Edit the two `#pragma` lines in `solution.c`.
2. Run `bash check.sh` in this folder (tests are in `TESTS.md`).
3. Tell the teacher "done" (or ask for a hint) in the chat.

## Result

2026-09-25 · **PASS** (200 runs × 8 threads, n=100000 and n=1, base 10 and 0) · **grade 4/5**

- `private(tmp)`, `lastprivate(last)` and `firstprivate(base)` are exactly right: tmp is scratch, last must carry the final iteration out, base must start at the caller's value in every thread.
- Correct beyond the tests: `firstprivate(a, b, n, scale)` and `firstprivate(slots)` copy the *pointers*, so each thread's copy still points at the same shared arrays; writes through `b[i]` and `slots[...]` land in shared memory. This is the private-pointer / shared-pointee idea from n1/n6, used correctly.
- Wart: for read-only variables (`a`, `n`, `scale`) and for pointers only used to reach shared data (`b`, `slots`), `shared(...)` states the intent. `firstprivate` says "each thread needs its own initialized copy", which a reader then has to reason away. Reference: `shared(a, b, n, scale) private(tmp) lastprivate(last)` and `shared(slots) firstprivate(base)`.
- Loop variable `i` needs no clause even under `default(none)`: the loop variable of an `omp for` is predetermined private.
