---
name: checkpoint
description: Save the lesson state right now - what was just covered, the learner's results and the exact next step - so nothing is lost if the session ends or the context is compacted. Use when the learner types /checkpoint, says they need to stop, or before any long detour.
argument-hint: [optional note]
---

# Checkpoint

1. If no topic is active, say so and stop.
2. Record, in this order, whatever applies since the last checkpoint:
   - `python scripts/state.py node-done <id> "<summary>" --check <type>` or `node-shaky <id> "<why>"` for any node whose check completed.
   - `python scripts/state.py edge "..."` for any new finding about the learner's level.
   - `python scripts/state.py checkpoint "<one line: what was just taught or asked and the result>"`.
   - `python scripts/state.py next "<the exact next step, specific enough to resume cold>"`.
3. If the learner is stopping for now, also run `python scripts/state.py pause` and tell them to resume with `/teach continue` or `python scripts/state.py resume <slug>` next time.
4. Confirm in one line. Do not summarise the lesson back to the learner.
