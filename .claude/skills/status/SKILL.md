---
name: status
description: Show where the learner stands - active topic, plan progress, next step, all topics, and what is due for review. Use when the learner asks "where were we", "what's next", "what's due", or types /status.
---

# Status

Run both and present the result compactly, with dates:

```
python scripts/state.py show
python scripts/state.py topics
python scripts/srs.py stats
python scripts/srs.py forecast --days 7
```

Then say in one or two sentences what you recommend doing now: continue the active topic at NEXT, run `/review` if cards are due, or start something new. Do not start teaching from this skill; wait for the learner's choice.
