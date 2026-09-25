# Learning for Lunch

**A personal AI tutor inside Claude Code, combining structured lessons, rubric-based assessment, coding practice, and spaced repetition.**

Learning for Lunch turns a Claude Code session into a persistent learning workspace. The tutor assesses your starting point, builds a plan around your goal, checks your understanding, and schedules future reviews. Lesson progress and notes are stored outside the conversation to support continuity across sessions.

## Features

- **Personalized lesson plans** — Probe your level, clarify your goal, and organize concepts in a dependency graph.
- **Short-answer assessment** — Explain ideas in your own words. The tutor stores a model answer and key points before asking, then grades your response on a 0–5 scale.
- **Spaced repetition** — Review checked concepts using an SM-2 scheduling implementation.
- **Practical coding exercises** — Apply programming concepts through tasks, starter files, and tests under `exercises/`.
- **Persistent lesson state** — Store the active topic, plan, progress, and next step in files that can be loaded into later sessions.
- **Obsidian integration** — Mirror lesson exchanges into dated Markdown notes with Mermaid diagrams and SVG assets.
- **Research and diagram agents** — Delegate topic research and visual verification to specialized Claude Code subagents.

## How a lesson works

1. **Start Claude Code.** Run `claude` from the project directory. A `SessionStart` hook injects the current date, active topic, lesson progress, and due reviews.
2. **Choose a topic.** Run `/teach <topic>`. The tutor uses quick multiple-choice questions to assess your level and asks what you want to achieve.
3. **Approve a plan.** The tutor researches the topic and proposes a dependency graph. Teaching begins after you approve it.
4. **Work through each concept.** Each node follows a **motivate → establish → connect → check** loop. Key concepts require short answers; programming topics include coding tasks.
5. **Record progress.** Scripts save checkpoints and the next step. A Stop hook mirrors lesson exchanges into the configured note.
6. **Review and continue.** Checked concepts become review cards. Use `/review` for due cards, `/status` for progress, and `/teach continue` to pick up the lesson.

The tutor performs the assessment; the Python scripts store results and calculate review dates.

## Getting started

### Requirements

- Claude Code
- Python 3
- **Node.js 22.12 or later** and npm, matching the requirements of Puppeteer in the committed dependency lockfile
- Chrome or Chromium available on `PATH`, or configured through `CHROME_PATH`
- Bash for the setup examples and exercise runners
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

Relative paths resolve from the project root. An empty `timezone` uses local system time; you can also supply a time zone such as `Europe/Oslo`.

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
| `/review [topic] [--limit N]` | Review due cards, optionally filtered by topic and limited in number. |
| `/code-task` | Create or check a coding exercise. |
| `/visualize <idea>` | Create a diagram through the render-and-inspect workflow. |
| `/status` | Show progress and due reviews. |
| `/checkpoint [note]` | Save the current lesson state. |

You can also inspect the underlying data from the terminal:

```bash
python3 scripts/state.py show
python3 scripts/state.py topics
python3 scripts/srs.py stats
python3 scripts/srs.py forecast
python3 scripts/exercise.py list
```

To resume a specific paused topic directly:

```bash
python3 scripts/state.py resume <topic-slug>
```

## Architecture

Claude Code provides the teaching interface. Skills define the lesson and assessment workflows, while Python scripts handle persistence, scheduling, and exercise execution.

| Component | Responsibility |
| --- | --- |
| Tutor and skills | Probe knowledge, plan lessons, teach concepts, assess answers, and provide feedback. |
| Research and diagram agents | Research topics and create visually verified diagrams. |
| State scripts | Record topics, dependency plans, checkpoints, and the next teaching step. |
| Review scheduler | Store cards and apply SM-2 scheduling to recorded grades. |
| Hooks | Inject session context, mirror transcripts, and prompt overdue checkpoints. |
| Markdown notes | Provide a readable lesson record, including explanations, questions, and diagrams. |

### Project structure

| Path | Purpose |
| --- | --- |
| `.claude/settings.json` | Session model, permissions, and hook configuration. |
| `.claude/skills/` | Teaching, review, coding, visualization, status, and checkpoint workflows. |
| `.claude/agents/` | Researcher, Mermaid, and SVG agent definitions. |
| `scripts/state.py` | Topic, plan, progress, and checkpoint management. |
| `scripts/srs.py` | Review cards and scheduling. |
| `scripts/exercise.py` | Exercise scaffolding and test execution. |
| `scripts/session_log.py` | Transcript mirroring into lesson notes. |
| `scripts/render.py` | Mermaid and SVG rendering for visual inspection. |
| `scripts/learnlib.py` | Shared configuration, path, date, and persistence helpers. |
| `scripts/selftest.sh` | Smoke test for the core workflows. |
| `state/` | Lesson state, review deck, and readable progress summary. |
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

