---
name: code-task
description: Create, validate, check and grade a coding exercise for the learner. Use during a programming lesson when a node is best proven by writing code, at the end of a programming topic, or when the learner asks for a coding task or says they are done with one.
argument-hint: [new <name> | check <folder> [--file retry.c]]
---

# Coding tasks

A coding task proves the learner can build with an idea. Two sizes: short activities (predict the output, run it, explain, modify one line; 3-8 minutes) between nodes of a long programming topic, and a few substantial tasks (10-25 minutes) aligned to the goal. Prepare tasks during preparation from the node's `code_exercise` spec; the live turn only hands them out and grades them.

## Environment

`python3 scripts/exercise.py env` reports the compiler and OpenMP support once per machine. For C the checks use `gcc -std=c11 -O2 -Wall -Wextra -fopenmp`, a timeout, several input sizes and thread counts, a serial oracle and numeric tolerances.

## Create (preparation)

1. `python3 scripts/exercise.py new --topic <slug> --name <kebab> --lang c|python|js --title "Readable title"`
2. Write `README.md`: task, inputs/outputs, constraints, two or three examples, which node it exercises. No solution.
3. Write the test file (visible to the learner): the oracle, sizes, thread counts, tolerances. For C keep `test_main.c`'s shape.
4. Adjust the starter's signature. The starter never contains the solution.
5. Under `.reference/` (never shown to the learner): `reference.c` (or .py/.js), at least one deliberately flawed variant, and `expect.json` with the expected verdicts. `python3 scripts/exercise.py validate <folder>` must pass before the task is handed out. A racy variant that passes by luck is reported as unreliable: the grade must then rest on the learner's reasoning about synchronization, not on green tests.
6. `perf.sh` (C) is an optional experiment, never part of the grade.

## Hand out

`python3 scripts/state.py ask <node> --check <code-check-id>` when the node's prep has a code check (it records the pending task); otherwise `python3 scripts/state.py next "waiting for <folder>"`. Tell the learner the folder, that they edit the starter in their editor, run `bash check.sh`, and say "done" or ask for a hint. Hints via `python3 scripts/state.py hint`; give the smallest one that unblocks. Never write the solution into their file.

## Check and grade

1. `python3 scripts/exercise.py check <folder>` (a review retry: `--file retry-<date>.c`; the original is never overwritten, and every checked file is copied under `.attempts/`).
2. Read their file. Review as a mentor: does it use the idea the task targets, is it correct beyond the tests (data ownership, synchronization, edge sizes), is it clear? One or two concrete improvements at most. For parallel code, require the reasoning: "the race did not show up" is not correctness.
3. Grade 0-5: 5 passes and uses the idea cleanly with sound reasoning, 4 passes with a wart, 3 passes only after a hint or with a real flaw in reasoning, 2 fails but the approach is right, 1 fails, 0 not attempted. A timing result never lowers a correct solution's grade.
4. Append the result to the README's "Result" section (date, verdict, feedback, grade) and set `status: done`.
5. Record with one command: `python3 scripts/state.py record < result.json` (result, quality, assistance if any, misconception if any). If the task was not posed with `ask`, add the card by hand: `python3 scripts/srs.py add --topic <slug> --node <id> --type code --task "<folder>" --q "<one-line task>" --a "<what a correct approach must contain>"` then `srs.py grade <id> <q> --kind initial`.
