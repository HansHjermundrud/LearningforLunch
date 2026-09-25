---
title: "Race-free histogram: pick the construct"
date: 2026-09-25
topic: parallel-programming-with-openmp
lang: c
status: open
---
# Race-free histogram: pick the construct

_Created 2026-09-25 · topic `parallel-programming-with-openmp` · language c_

## Task

Node: **n7 · Synchronization**.

`solution.c` counts how many values of `x` fall into each of `bins` bins (bin = `x[i] % bins`), adding to whatever counts `hist` already holds, exactly like the serial loop. As written the loop has a data race on `hist[b]`.

1. Make the loop race-free with the **cheapest construct that suffices**. Keep the `parallel for`.
2. In your "done" message, explain in one short paragraph which two accesses were unordered before, and what your construct does to them. The tests can pass by luck for a racy program, so the grade rests on this explanation as much as on the green run.
3. Optional (not graded): `bash perf.sh` compares 1, 2, 4 and 8 threads. Try the same with a `critical` around the whole body and compare.

Constraints: do not change the signature, `test_main.c`, or the meaning (prior counts in `hist` must be preserved).

## Examples

```
x = {0, 1, 2, 3, 4}, bins = 3, hist = {0, 0, 0}   -> hist = {2, 2, 1}
x = {5, 5},          bins = 3, hist = {1, 1, 1}   -> hist = {1, 1, 3}
```

## How to work

1. Edit `solution.c`.
2. Run `bash check.sh` in this folder (the oracle and sizes are in `test_main.c`).
3. Tell the teacher "done" with your explanation, or ask for a hint.
4. Optional, not graded: `bash perf.sh`.

## Result

(Filled in by the teacher after review: date, passed/failed, feedback, grade 0-5.)
