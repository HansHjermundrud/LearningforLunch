# learning

A personal AI tutor that runs inside Claude Code. A port and extension of
[amosblomqvist/learn](https://github.com/amosblomqvist/learn) with four additions:
short-answer questions graded against a committed rubric, a spaced-repetition deck,
coding tasks, and an external memory that keeps long lessons from losing themselves.

## How a lesson works

1. `claude` in this folder. A SessionStart hook injects the date, the active topic and due reviews.
2. `/teach <topic>` starts a lesson. The teacher probes your level with quick multiple-choice
   questions, pins down your goal, researches the topic, and presents a plan as a dependency graph.
3. You approve the plan. Each node is taught in a motivate / establish / connect / check loop.
   Load-bearing nodes and the end of every topic are checked with short answers in your own words.
   Programming topics get coding tasks under `exercises/`.
4. Everything you and the teacher write is mirrored into a dated note in your Obsidian vault.
   Diagrams render there too (Mermaid inline, SVG files in the diagram folder).
5. Every checked node becomes a review card. `/review` runs the cards that are due (SM-2 scheduling).
6. `/status` shows where you stand; `/checkpoint` saves the state when you need to stop.

## Setup

```bash
git clone <this repo> ~/learning && cd ~/learning
cd tools && PUPPETEER_SKIP_DOWNLOAD=1 npm install && cd ..   # mermaid renderer (uses system Chrome)
```

Requirements: Claude Code, python3, Node 18+, and Chrome or Chromium on PATH (for diagram
verification). `rsvg-convert` (package `librsvg2-bin`) is optional.

Point the note folders at your vault in `learn.config.json`:

```json
"notesDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning",
"vizDir":   "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/viz",
"reviewsDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/reviews"
```

Then edit `LEARNER.md` and run `claude`.

## Commands

| Command | What it does |
|---|---|
| `/teach <topic>` or `/teach continue` | Start or resume a lesson |
| `/review [topic] [--limit N]` | Review due cards |
| `/code-task` | Create or check a coding exercise |
| `/visualize <idea>` | Add one verified diagram |
| `/status` | Progress and due reviews |
| `/checkpoint [note]` | Save state now |

Scripts can also be run directly: `python3 scripts/state.py show`, `python3 scripts/srs.py stats`,
`python3 scripts/srs.py forecast`, `python3 scripts/exercise.py list`.

## Layout

```
.claude/settings.json   model pin, permissions, hooks (SessionStart, Stop, PreCompact)
.claude/skills/         teach, review, code-task, visualize, status, checkpoint
.claude/agents/         researcher, mermaid-maker, svg-maker
scripts/                state.py, srs.py, exercise.py, render.py, hooks
state/                  state.json, deck.json, progress.md
notes/                  default note folder when no vault is configured
exercises/              coding tasks
tools/                  mermaid-cli (node_modules ignored by git)
LEARNER.md              your profile and preferences
CLAUDE.md               instructions the tutor reads every session
```

## Changing models

The teacher uses the session model, pinned in `.claude/settings.json` (`"model": "opus"`).
Override per session with `/model`. Subagent models are the `model:` line in each file under
`.claude/agents/`.
