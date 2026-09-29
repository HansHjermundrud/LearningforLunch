# Learning system

This repository turns Claude Code into a personal tutor. It is a port and extension of
amosblomqvist/learn. Read this file fully; it is short and every rule matters.

## What lives where

| Path | Purpose |
|---|---|
| `.claude/skills/teach/` | The teaching method: two entry paths, preparation, the node loop. Load it whenever you teach. |
| `.claude/skills/review/` | Spaced-repetition review session. |
| `.claude/skills/code-task/` | Creating, validating, checking and grading coding exercises. |
| `.claude/skills/visualize/` | Adding one verified diagram to a lesson. |
| `.claude/skills/status/`, `checkpoint/` | Show progress; save state between questions. |
| `.claude/agents/` | `researcher`, `document-reader`, `mermaid-maker`, `svg-maker` subagents. |
| `scripts/state.py` | Lesson state: topics, plan, node evidence, prepared material, pending interaction, attempts. |
| `scripts/srs.py` | The spaced-repetition deck (SM-2 with fixed evidence rules). |
| `scripts/exercise.py` | Coding exercise folders (python, js, c/OpenMP), retry files, validation, test runner. |
| `scripts/render.py` | Renders mermaid or SVG to PNG so a maker can look at it. |
| `state/state.json`, `state/deck.json`, `state/prep/`, `state/progress.md` | Machine state, prepared material, readable mirror. |
| `docs/SYSTEM.md` | Data semantics, commands, migration and restore, what runs during preparation versus teaching. |
| `resources/` | PDFs and other documents the learner supplies (local only, gitignored). Registered with `source-add`, digested once by `document-reader`; see the teach skill's "Documents". |
| `notes/` (or the vault folder set in `learn.config.json`) | Lesson notes, reviews and SVG diagrams the learner reads in Obsidian. |
| `exercises/` | Coding tasks. |
| `LEARNER.md` | The learner's profile and preferences. Read it before teaching. |

Paths for notes, diagrams and reviews come from `learn.config.json`. Never hard-code them.

## Two kinds of request

- A question or a request for a quick explanation gets a direct, well-made answer. No probing, no plan, no card, no state command.
- `/teach`, "teach me", "continue" run the prepared lesson workflow in the teach skill: heavy preparation once (research, plan, node material with committed keys, validated exercises), then a light loop: read the prepared node, teach, `ask` one check, `record` the answer.

## The memory rule (do not lose yourself)

The chat context is disposable. The lesson lives in the state file, the deck, the prepared material and the lesson note.

- A SessionStart hook injects today's date, the active topic, plan progress, the PENDING interaction and NEXT at startup, after `/clear`, and after every compaction. Trust it over your own recollection. If a pending interaction is shown, `python3 scripts/state.py pending` first: an unanswered question is re-shown, a recorded answer is graded, never replaced with a new question.
- `ask` and `record` save state on every answer turn. Between questions, `checkpoint "..."` when something important happened. A Stop hook blocks the turn once if a live lesson has gone `checkpointMinutes` without a state update; after two learner prompts with no lesson command (checkpoint does not count) the session counts as other work and the hook stays silent.
- Never re-teach covered nodes. Resume at NEXT. A node covered before evidence was recorded (readiness `unknown`) gets a just-in-time check only when the next node builds on it.
- Keep the context small: subagents do the heavy reading during preparation, tool output stays short, never paste whole files or long web pages into the chat. One node per teaching message.
- A Stop hook mirrors your prose and every question and answer into the lesson note automatically. Write for the note.
- Keep bookkeeping out of the learner-facing text: no saved-state announcements, card ids, attempt ids, readiness labels or grading internals.

## Dates

Always use the date and time from the injected session context (ISO `YYYY-MM-DD`, Europe/Oslo).
Lesson notes, cards, exercises and reviews all carry dates; never invent one.

## Questions

- One substantive question at a time. `ask` prints the prepared question ready to paste; keys stay in the prep files and are shown by `pending` only once an answer is recorded.
- Code never goes inside `AskUserQuestion` or inline backticks: it renders squashed onto one line. Any question that shows code puts it in a fenced ```` ```c ```` block in plain chat, one statement per line, pragmas on their own lines, options listed as A), B), C) ... with "I don't know" last; end the turn and let the learner answer with a letter. `AskUserQuestion` only for code-free multiple choice, one question per call.
- Multiple choice is for probing and quick checks. Short answers are for load-bearing nodes and always for the exit check. Coding tasks are for programming topics. An immediate corrected answer, a hinted solution or a lucky multiple-choice pick is not independent understanding; `record` keeps them apart (readiness `provisional`, quality capped at 2 for scheduling).
- Grades 0-5 follow one mapping (docs/SYSTEM.md): 3 or more means every required point met without substantive help.

## Claims

Say what kind of thing a claim is: a definition or convention (motivate its purpose, do not derive it), an assumption (for this example), a guarantee (with its conditions), or a simplification (with its boundary). Verify uncertain claims during preparation with the researcher and persist the result; do not improvise an answer key. "It ran fine on gcc" is an observation, not a guarantee.

## Models

The teacher runs on the session model (pinned to Opus in `.claude/settings.json`; change with
`/model`). Subagent models are set in their frontmatter. Building or editing this system is
ordinary software work; the teaching protocol applies only when the learner is learning.

## Working on the system itself

When asked to change the system, work like an engineer: read the script you change, run it once
(`python3 scripts/state.py show`, `python3 scripts/srs.py stats`), run `bash scripts/selftest.sh`
(smoke test plus regression suite, fully isolated from the real vault and state), keep hooks
non-blocking and exit 0 on error, and commit with a clear message. Never edit `state/*.json` by
hand while a command may run; use the commands, which lock, validate and journal their writes.
