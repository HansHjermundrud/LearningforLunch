# Learner profile

The teacher reads this at the start of every lesson. Edit it freely; it is the one
place to describe how you learn best. Keep it short.

## About me

- Background: (e.g. "informatics student, comfortable with Python, rusty on maths")
- Languages I code in: Python, JavaScript, C/C++
- Native language: (the lesson is written in English unless you say otherwise)

## Current goal

- Learn parallel programming with OpenMP: the shared-memory model, parallel regions, work-sharing
  loops, data scoping, synchronization, reductions and tasks, and how to reason about speedup
  and correctness (race conditions, false sharing, load balance). Exercises in C with `-fopenmp`.

## How I learn

- I want understanding, not recall. Derive things from foundations I already accept.
- Prefer Socratic when I can plausibly reason my way there; narrate when I can't.
- Multiple choice is fine for warm-ups and quick checks. When a node matters, or a topic ends,
  ask me to explain in my own words and grade that honestly.
- For programming topics, make me write code.

## Session preferences

- Typical session length: 45-60 minutes
- Energy signals: if I answer with one word twice in a row, switch to expository and shorten.
- Diagrams: yes, when structure or geometry is the point.

## Standing notes from past lessons

(The teacher may append one-line observations here, dated, e.g. "2026-09-24: confuses 'axiom' with 'definition'.")
- 2026-09-24: C pointers: tends to read `r = q` as "r points to q" and blurs pointer vs pointee. Spell out address vs value when pointers appear.
- 2026-09-24: Wants concrete code shown, not a verbal description of a code change.
- 2026-09-24: Multi-question AskUserQuestion calls led to accidental submits twice. Ask one gradable MC per call.
- 2026-09-25: Believes a thread's stack is off-limits to other threads ("private" = inaccessible). Missed this card twice, with a different wrong answer each time. Stress that there is one address space: privacy is about names, and a pointer reaches anything.
- 2026-09-25: Code in AskUserQuestion renders unreadably. Show code as a fenced block in chat with lettered options instead.
- 2026-09-25: Calls any nondeterminism a race (said private(last) still races because 'we don't know which thread writes last'). Re-check against the definition: same location, >=1 write, no ordering.
