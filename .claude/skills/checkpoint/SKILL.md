---
name: checkpoint
description: Save the lesson state right now - what was just covered, the learner's results and the exact next step - so nothing is lost if the session ends or the context is compacted. Use when the learner types /checkpoint, says they need to stop, or before any long detour.
argument-hint: [optional note]
---

# Checkpoint

1. If no topic is active, say so and stop.
2. If a question is waiting: `python3 scripts/state.py pending`. An answer that was given but not graded is graded now with `record`; a question the learner has not answered stays pending (that is already saved).
3. Otherwise record what happened since the last save with one command: `python3 scripts/state.py checkpoint "<what was just taught or asked and the result>"`, plus `next "<the exact next step, specific enough to resume cold>"` only if NEXT is wrong. New findings about the learner: `edge "..."`.
4. If the learner is stopping for now: `python3 scripts/state.py pause`, and tell them `/teach continue` resumes.
5. Confirm in one short line. Do not summarise the lesson back to the learner.
