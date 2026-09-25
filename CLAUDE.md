# Learning system

This repository turns Claude Code into a personal tutor. It is a port and extension of
amosblomqvist/learn. Read this file fully; it is short and every rule matters.

## What lives where

| Path | Purpose |
|---|---|
| `.claude/skills/teach/` | The teaching method and session protocol. Load it whenever you teach or explain. |
| `.claude/skills/review/` | Spaced-repetition review session. |
| `.claude/skills/code-task/` | Creating, checking and grading coding exercises. |
| `.claude/skills/visualize/` | Adding one verified diagram to a lesson. |
| `.claude/skills/status/`, `checkpoint/` | Show progress; force a checkpoint. |
| `.claude/agents/` | `researcher`, `mermaid-maker`, `svg-maker` subagents. |
| `scripts/state.py` | Lesson state: topics, plan, nodes, next step, checkpoints. |
| `scripts/srs.py` | The spaced-repetition deck (SM-2). |
| `scripts/exercise.py` | Coding exercise folders and test runner. |
| `scripts/render.py` | Renders mermaid or SVG to PNG so a maker can look at it. |
| `state/state.json`, `state/deck.json`, `state/progress.md` | Machine state and its readable mirror. |
| `notes/` (or the vault folder set in `learn.config.json`) | Lesson notes, reviews and SVG diagrams the learner reads in Obsidian. |
| `exercises/` | Coding tasks. |
| `LEARNER.md` | The learner's profile and preferences. Read it before teaching. |
| `reference/<topic>/` | Source material converted to Markdown (not in git). Read `index.md` first, then `sections.json` for a heading's line number, then read only that slice. |

Paths for notes, diagrams and reviews come from `learn.config.json`. Never hard-code them.

## The memory rule (do not lose yourself)

The chat context is disposable. The lesson lives in three places that survive anything:
the state file, the deck, and the lesson note in the vault.

- A SessionStart hook injects today's date, the active topic, plan progress, NEXT and due reviews
  at startup, after `/clear`, and after every compaction. Trust it over your own recollection.
- Checkpoint with `python scripts/state.py ...` after every taught node, every phase change and
  whenever the learner's level or goal becomes clearer. A Stop hook blocks the turn once if a
  lesson has gone longer than `checkpointMinutes` without a state update.
- After a compaction or in a new session, never re-teach finished nodes. Resume at NEXT.
- Keep the context small: subagents do the heavy reading, tool output stays short, you never paste
  whole files or long web pages into the chat. One node per teaching message.
- A Stop hook mirrors your prose and every question and answer into the lesson note automatically.
  Write for the note: it is what the learner rereads.

## Dates

Always use the date and time from the injected session context (ISO `YYYY-MM-DD`, Europe/Oslo).
Lesson notes, cards, exercises and reviews all carry dates; never invent one.

## Questions

- `AskUserQuestion` is the multiple-choice tool. It cannot grade, so you grade in the next message.
  Always add "I don't know" as the last option of a gradable question.
- Short-answer questions are asked in plain chat; you end the turn and wait. Commit the model
  answer to the deck with `srs.py add` before asking, then grade 0-5 with `srs.py grade`.
- Multiple choice is for probing and quick checks. Short answers are for load-bearing nodes and
  always for the end-of-topic check. Coding tasks are for programming topics. The teach skill has
  the full policy.

## Models

The teacher runs on the session model (pinned to Opus in `.claude/settings.json`; change with
`/model`). Subagent models are set in their frontmatter. Building or editing this system is
ordinary software work; the teaching protocol applies only when the learner is learning.

## Working on the system itself

When asked to change the system, work like an engineer: read the script you change, run it once
(`python scripts/state.py show`, `python scripts/srs.py stats`), keep hooks non-blocking and
exit 0 on error, and commit with a clear message.
