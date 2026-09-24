---
name: code-task
description: Create, check and grade a coding exercise for the learner. Use during a programming lesson when a node is best proven by writing code, at the end of a programming topic, or when the learner asks for a coding task or says they are done with one.
argument-hint: [new <name> | check <folder>]
---

# Coding tasks

A coding task proves the learner can build with an idea, not just recognise it. Keep each task small enough to finish in 10-25 minutes and aimed at exactly one node of the plan.

## Create

1. Scaffold the folder:
   `python3 scripts/exercise.py new --topic <topic-slug> --name <kebab-name> --lang python|js|other --title "Readable title"`
2. Write the task into `README.md` under "Task" and "Examples": what to build, inputs, outputs, constraints, and two or three concrete examples. State which node of the plan it exercises. Do not include the solution.
3. Replace the placeholder test with real cases (`test_solution.py` or `solution.test.js`). Tests are visible to the learner; that is fine. Cover the examples plus one edge case.
4. Adjust the starter file's function signature to match the task.
5. Tell the learner the folder path, that they edit the starter file in their own editor, run `bash check.sh` in that folder, and say "done" (or ask for a hint) when ready.
6. Checkpoint: `python3 scripts/state.py next "waiting for coding task <folder>"`.

The learner may use any editor. Never write the solution into their file. Hints are allowed; give the smallest one that unblocks.

## Check and grade

When the learner says done:

1. `python3 scripts/exercise.py check <folder>`.
2. Read their solution file. Review it as a mentor, not a linter: does it use the idea the task targets, is it correct beyond the tests, is it clear? One or two concrete improvements at most.
3. Grade 0-5: 5 passes and uses the idea cleanly, 4 passes with a wart, 3 passes only after a hint or with a real flaw, 2 fails but the approach is right, 1 fails, 0 not attempted.
4. Append the result to the "Result" section of the README with the date, verdict, feedback and grade, and set `status: done` in its frontmatter.
5. Add a review card so the task comes back later:
   `python3 scripts/srs.py add --topic <slug> --node <id> --type code --task "<folder>" --q "<one-line task summary>" --a "<what a correct approach must contain>"`
   then `python3 scripts/srs.py grade <id> <q>`.
6. Record the node: `python3 scripts/state.py node-done <id> "<summary>" --check code` (or `node-shaky`).
