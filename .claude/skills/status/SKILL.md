---
name: status
description: Show where the learner stands - active topic, plan progress, next step, all topics, and what is due for review. Use when the learner asks "where were we", "what's next", "what's due", or types /status.
---

# Status

Run and present compactly, with dates:

```
python3 scripts/state.py show --full
python3 scripts/state.py topics
python3 scripts/srs.py stats
python3 scripts/srs.py forecast --days 7
```

Translate the node marks for the learner (✓ solid, ◐ provisional, ~ needs repair, ? covered before evidence was recorded, · not yet). Then say in one or two sentences what you recommend now: continue at NEXT, `/review` if cards are due, or something new. Do not start teaching from this skill; wait for the learner's choice.
