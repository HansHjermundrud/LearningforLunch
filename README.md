# learning

A personal AI tutor that runs inside Claude Code. A port and extension of
[amosblomqvist/learn](https://github.com/amosblomqvist/learn): short-answer questions graded
against committed keys, a spaced-repetition deck, coding tasks (Python, JavaScript, C/OpenMP),
and an external memory that keeps long lessons from losing themselves. Preparation is heavy and
happens once; the live lesson is a light conversational loop.

## How a lesson works

1. `claude` in this folder. A SessionStart hook injects the date, the active topic, any open
   question and what is due for review.
2. A quick question gets a direct answer. `/teach <topic>` starts a lesson: a short probe, the
   goal, research in one or two batched calls, a plan as a dependency graph you approve once, and
   prepared material for the next few nodes (objective, outline, verified claims, misconceptions,
   checks with committed keys and hint ladders, validated exercises).
3. Each node is taught in one or two messages: motivate, explain, connect, one check. The teacher
   grades honestly against the committed key and saves the turn with one command. Hints are
   recorded automatically; an assisted or partial answer counts as provisional, not as mastery.
4. Everything you and the teacher write is mirrored into a dated note in your Obsidian vault.
5. Durable concepts become review cards. `/review` runs what is due within a time budget.
6. `/status` shows where you stand; `/checkpoint` saves between questions.

`docs/SYSTEM.md` documents the data (coverage / readiness / retention per node, attempts, the
pending interaction), the grade mapping, the scheduling rules, durability (lock, journal,
backups, migration) and every command.

## Setup

```bash
git clone <this repo> ~/learning && cd ~/learning
cd tools && PUPPETEER_SKIP_DOWNLOAD=1 npm install && cd ..   # mermaid renderer (uses system Chrome)
```

Requirements: Claude Code, python3, Node 18+, Chrome or Chromium on PATH (diagram
verification), gcc with OpenMP for C exercises (`python3 scripts/exercise.py env` checks).

Point the note folders at your vault in `learn.config.json`:

```json
"notesDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning",
"vizDir":   "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/viz",
"reviewsDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/reviews"
```

Then edit `LEARNER.md` and run `claude`. Optional keys: `reviewMinutes` (default 10),
`checkpointMinutes` (12), `backupsKeep` (10).

## Commands

| Command | What it does |
|---|---|
| `/teach <topic>` or `/teach continue` | Start or resume a lesson |
| `/review [topic] [--limit N]` | Review due cards within the time budget |
| `/code-task` | Create, validate or check a coding exercise |
| `/visualize <idea>` | Add one verified diagram |
| `/status` | Progress and due reviews |
| `/checkpoint [note]` | Save state now |

Scripts can also be run directly: `python3 scripts/state.py show --full`, `next-node`, `pending`,
`python3 scripts/srs.py stats`, `forecast`, `python3 scripts/exercise.py list`.

Upgrading from the v1 state files: `python3 scripts/state.py migrate` (byte-for-byte backups land in
`state/backups/`; `restore --list` shows them). The migration is idempotent and runs automatically
in memory for reads and on the first write.

## Tests

`bash scripts/selftest.sh` runs a smoke test in a temporary copy with its own configuration, then
the regression suite (`python3 -m unittest discover -s scripts/tests`). Neither touches the
configured vault or the live state.

## Layout

```
.claude/settings.json   model pin, permissions, hooks (SessionStart, Stop, PreCompact)
.claude/skills/         teach, review, code-task, visualize, status, checkpoint
.claude/agents/         researcher, mermaid-maker, svg-maker
scripts/                learnlib.py, state.py, srs.py, exercise.py, render.py, hooks, tests/
state/                  state.json, deck.json, prep/<topic>/<node>.json, progress.md, backups/
docs/                   SYSTEM.md (data and commands), SCENARIOS.md (expected tool calls per turn)
notes/                  default note folder when no vault is configured
exercises/              coding tasks (README, starter, tests, .reference/, .attempts/)
tools/                  mermaid-cli (node_modules ignored by git)
LEARNER.md              your profile and preferences
CLAUDE.md               instructions the tutor reads every session
```

## Changing models

The teacher uses the session model, pinned in `.claude/settings.json` (`"model": "opus"`).
Override per session with `/model`. Subagent models are the `model:` line in each file under
`.claude/agents/`.
