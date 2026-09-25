---
title: "Histogram as a reduction"
date: 2026-09-25
topic: parallel-programming-with-openmp
lang: c
status: open
---
# Histogram as a reduction

_Created 2026-09-25 · topic `parallel-programming-with-openmp` · language c_

## Task

Node: **n8 · Reductions**.

`solution.c` is the race-free atomic histogram from the previous task. Every element now contends for shared memory. Rewrite it so that **no atomic or critical runs per element**:

- either a reduction over the array section `hist[0:bins]`,
- or an explicit per-thread histogram, combined into `hist` once at the end.

The result must stay identical to the serial loop, including the prior counts already in `hist`. In your "done" message, explain in one paragraph where the combine happens and why the prior contents of `hist` are preserved (what the private copies start from).

Constraints: do not change the signature or `test_main.c`. `check.sh` refuses a file that still uses `atomic` in the loop.

## Examples

```
x = {0, 1, 2, 3, 4}, bins = 3, hist = {0, 0, 0}   -> hist = {2, 2, 1}
x = {5, 5},          bins = 3, hist = {1, 1, 1}   -> hist = {1, 1, 3}   (prior counts kept)
```

## How to work

1. Edit `solution.c`.
2. Run `bash check.sh` in this folder.
3. Tell the teacher "done" with your explanation, or ask for a hint.
4. Optional, not graded: `bash perf.sh`, and compare with the atomic version's timings.

## Result

(Filled in by the teacher after review: date, passed/failed, feedback, grade 0-5.)
