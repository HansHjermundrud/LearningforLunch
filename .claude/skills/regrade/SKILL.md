---
name: regrade
description: Correct the last grade when the learner disputes it - "that was a bit critical, make it a 4", "change that to a 3", "correct the last grade". Fixes the attempt, its review card's schedule, and the node's readiness or retention in one command. Use for /regrade or any such request during a lesson or review.
argument-hint: <grade 0-5> [why]
---

# Regrade

The learner's request to change their own grade is legitimate; a grade they think is too harsh should not drive their schedule.

1. Take the grade they asked for (0-5). If they only said "too harsh" without a number, ask which grade in one short line.
2. Run: `python3 scripts/state.py regrade <q> --reason "<the learner's reason, short>"`. It corrects the most recent grade, from a lesson check or a review card alike. For an older one, `--target <attempt or card id>` (find it with `state.py history` or `srs.py history <card>`).
3. If it refuses because the answer was given with hints: 3 or more means no substantive help. Say so in one sentence and ask whether the hint was really only a rephrasing of the question. If yes (or the learner holds to it), rerun with `--independent`.
4. Confirm in one short line ("Changed to 4.") and carry on where you were: a waiting question stays waiting, the lesson resumes at NEXT. No ids, readiness labels or scheduling details.

Raising a grade to 3+ records that every required point was met; if you think the answer really missed one, say which in one sentence before regrading, then do what the learner decides. The original grade and the reason are kept in the attempt's `regrades`.
