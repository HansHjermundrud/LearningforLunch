# Learning for Lunch

**A personal AI tutor inside Claude Code, combining structured lessons, rubric-based assessment, coding practice, and spaced repetition.**

Learning for Lunch turns a Claude Code session into a persistent learning workspace. The tutor assesses your starting point, builds a plan around your goal, checks your understanding, and schedules future reviews. Lesson progress and notes are stored outside the conversation to support continuity across sessions.

The heavy work happens while preparing a lesson: research, verified claims, committed answer keys, and validated exercises. The live lesson stays conversational: one explanation, one check, one save per turn.

## Features

- **Personalized lesson plans** — Probe your level, clarify your goal, and organize concepts in a dependency graph.
- **Prepared lessons** — Before teaching, each node gets an objective, an outline, source-checked claims, likely misconceptions, and checks with committed answer keys and hint ladders.
- **Short-answer assessment** — Explain ideas in your own words. The tutor grades against the prepared key on a 0–5 scale. Hinted or incomplete answers count as provisional, not as mastery.
- **Spaced repetition** — Review durable concepts using SM-2, with safeguards so immediate reattempts and same-day repeats do not inflate the schedule.
- **Practical coding exercises** — Apply programming concepts through tasks, starter files, and tests under `exercises/`, including C with OpenMP.
- **Persistent lesson state** — Store the active topic, plan, per-node evidence, any open question, and the next step in files that survive restarts and context compaction.
- **Obsidian integration** — Mirror lesson exchanges into dated Markdown notes with Mermaid diagrams and SVG assets.
- **Research and diagram agents** — Delegate topic research and visual verification to specialized Claude Code subagents.

## How a lesson works

1. **Start Claude Code.** Run `claude` from the project directory. A `SessionStart` hook injects the current date, active topic, lesson progress, and due reviews.
2. **Choose a topic.** Run `/teach <topic>`. The tutor asks a few quick questions to place your level and clarifies what you want to achieve. A plain question outside `/teach` gets a direct answer instead.
3. **Approve a plan.** The tutor researches the topic, proposes a dependency graph, and prepares material for the next few concepts. You approve the plan once.
4. **Work through each concept.** Each node follows a **motivate → explain → connect → check** loop with one check by default. Key concepts require short answers; programming topics include coding tasks.
5. **Record progress.** Each answer is saved with one command: the attempt, the node's readiness, the review card, and the next step. A Stop hook mirrors lesson exchanges into the configured note.
6. **Review and continue.** Durable concepts become review cards. Use `/review` for due cards, `/status` for progress, and `/teach continue` to pick up the lesson, including a question that was still open.

The tutor performs the assessment; the Python scripts store results and calculate review dates. `docs/SYSTEM.md` documents the data model, grade mapping, scheduling rules, and commands.

## Getting started

### Requirements

- Claude Code
- Python 3
- **Node.js 22.12 or later** and npm, matching the requirements of Puppeteer in the committed dependency lockfile
- Chrome or Chromium available on `PATH`, or configured through `CHROME_PATH`
- Bash for the setup examples and exercise runners
- Optional: gcc with OpenMP support for C exercises (`python3 scripts/exercise.py env` checks)
- Optional: Obsidian for viewing lesson notes
- Optional: `rsvg-convert` from `librsvg2-bin` for SVG rendering

The commands below use a Bash shell, such as one available on Linux, macOS, or Windows through WSL.

### 1. Clone the repository

Replace the placeholder URL with this repository's clone URL:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git ~/learning
cd ~/learning
```

### 2. Install the diagram renderer

```bash
cd tools
PUPPETEER_SKIP_DOWNLOAD=1 npm ci
cd ..
```

This installs the locked dependencies without downloading Puppeteer's bundled browser. Rendering uses your system Chrome or Chromium installation.

### 3. Configure your folders

Set the folders in `learn.config.json` to match your workspace or Obsidian vault.

For a local setup, use:

```json
{
  "notesDir": "notes",
  "vizDir": "notes/viz",
  "reviewsDir": "notes/reviews",
  "exercisesDir": "exercises",
  "stateDir": "state",
  "timezone": "",
  "checkpointMinutes": 12
}
```

Relative paths resolve from the project root. An empty `timezone` uses local system time; you can also supply a time zone such as `Europe/Oslo`. Optional keys: `reviewMinutes` (review session budget, default 10) and `backupsKeep` (backups kept per state file, default 10).

For Obsidian, change the three note paths to folders inside your vault. For example, when accessing a Windows vault from WSL:

```json
{
  "notesDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning",
  "vizDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/viz",
  "reviewsDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/reviews"
}
```

These are the three fields to update in the full configuration. Keep `stateDir` and `exercisesDir` inside the repository.

### 4. Set up your learner profile

Edit `LEARNER.md` with your background, current goals, preferred programming languages, and learning preferences.

Then launch Claude Code from the project root:

```bash
claude
```

Start a lesson with a topic of your choice:

```text
/teach Python decorators
```

## Commands

| Command | Purpose |
| --- | --- |
| `/teach <topic>` | Start a lesson. |
| `/teach continue` | Continue the previous lesson. |
| `/review [topic] [--limit N]` | Review due cards within a time budget, optionally filtered by topic and limited in number. |
| `/code-task` | Create, validate, or check a coding exercise. |
| `/visualize <idea>` | Create a diagram through the render-and-inspect workflow. |
| `/status` | Show progress and due reviews. |
| `/checkpoint [note]` | Save the current lesson state. |

You can also inspect the underlying data from the terminal:

```bash
python3 scripts/state.py show --full
python3 scripts/state.py next-node
python3 scripts/state.py pending
python3 scripts/state.py topics
python3 scripts/srs.py stats
python3 scripts/srs.py forecast
python3 scripts/exercise.py list
```

To resume a specific paused topic directly:

```bash
python3 scripts/state.py resume <topic-slug>
```

### Upgrading existing state

State files from the first version migrate automatically in memory on read and on disk on the first write. To migrate explicitly:

```bash
python3 scripts/state.py migrate
python3 scripts/state.py restore --list
```

Byte-for-byte backups land in `state/backups/`. The migration is idempotent and never invents past answers.

## Tests

```bash
bash scripts/selftest.sh
```

This runs a smoke test in a temporary copy with its own configuration, then the regression suite in `scripts/tests/`. Neither touches your configured vault or live state.

## Architecture

Claude Code provides the teaching interface. Skills define the lesson and assessment workflows, while Python scripts handle persistence, scheduling, and exercise execution.

| Component | Responsibility |
| --- | --- |
| Tutor and skills | Probe knowledge, plan and prepare lessons, teach concepts, assess answers, and provide feedback. |
| Research and diagram agents | Research and verify topics during preparation, and create visually verified diagrams. |
| State scripts | Record topics, dependency plans, prepared material, per-node evidence, open questions, and the next teaching step. Writes are locked, validated, and journaled. |
| Review scheduler | Store cards and apply SM-2 scheduling to recorded grades. |
| Hooks | Inject a compact session snapshot, mirror transcripts, and prompt overdue checkpoints. |
| Markdown notes | Provide a readable lesson record, including explanations, questions, and diagrams. |

### Project structure

| Path | Purpose |
| --- | --- |
| `.claude/settings.json` | Session model, permissions, and hook configuration. |
| `.claude/skills/` | Teaching, review, coding, visualization, status, and checkpoint workflows. |
| `.claude/agents/` | Researcher, Mermaid, and SVG agent definitions. |
| `scripts/state.py` | Topic, plan, preparation, evidence, pending question, and checkpoint management. |
| `scripts/srs.py` | Review cards, scheduling, and answer-key corrections. |
| `scripts/exercise.py` | Exercise scaffolding (Python, JavaScript, C/OpenMP), validation, and test execution. |
| `scripts/session_log.py` | Transcript mirroring into lesson notes. |
| `scripts/render.py` | Mermaid and SVG rendering for visual inspection. |
| `scripts/learnlib.py` | Shared configuration, date, schema, migration, locking, and persistence helpers. |
| `scripts/selftest.sh` | Isolated smoke test, followed by the regression suite. |
| `scripts/tests/` | Regression tests with temporary state and an injectable clock. |
| `state/` | Lesson state, review deck, prepared material (`prep/`), readable progress summary, and backups. |
| `docs/` | `SYSTEM.md` (data and commands) and `SCENARIOS.md` (expected tool calls per teaching turn). |
| `notes/` | Local note storage when configured with relative paths. |
| `exercises/` | Coding tasks, starter files, and tests. |
| `tools/` | Mermaid CLI dependencies and npm lockfile. |
| `learn.config.json` | Folder paths, time zone, and checkpoint interval. |
| `LEARNER.md` | Learner profile and preferences. |
| `CLAUDE.md` | Tutor instructions loaded each session. |

## Model configuration

The session model is configured in `.claude/settings.json`:

```json
"model": "opus"
```

Use `/model` inside Claude Code to change it for the current session. Subagent models are configured separately through the `model:` field in their files under `.claude/agents/`.

## Authors and acknowledgments

- **Main author:** Hans Hjermundrud
- **Co-author:** Sebastian Sjøen-Tollaksvik

As recorded in `CLAUDE.md`, this project is a port and extension of `amosblomqvist/learn`.

