# Learning for Lunch

Developed, configured and tested by:
**Main author: Hans Hjermundrud**
**Co-author: Sebastian Sjøen-Tollaksvik**

**A personal AI tutor for Claude Code, with structured lessons, rubric-based assessment, and spaced repetition.**

Learning turns a Claude Code session into a persistent learning workspace. It combines guided instruction, short-answer checks, practical coding exercises, and scheduled reviews, while keeping lesson notes and progress outside the conversation so you can pick up where you left off.

## Features

- **Personalized lessons** — Assess your starting level, define a learning goal, and follow a plan organized by concept dependencies.
- **Rubric-based assessment** — Explain concepts in your own words and receive feedback against a committed grading rubric.
- **Spaced repetition** — Turn checked concepts into review cards scheduled with the SM-2 algorithm.
- **Coding practice** — Apply programming concepts through exercises stored in `exercises/`.
- **Persistent learning state** — Preserve lesson progress and checkpoints across sessions and long conversations.
- **Obsidian notes** — Mirror both sides of the lesson into dated notes, with inline Mermaid diagrams and SVG assets.

## How it works

1. **Start a session.** Run `claude` from the project directory. A `SessionStart` hook provides the current date, active topic, and due reviews.
2. **Choose a topic.** Run `/teach <topic>`. The tutor uses quick multiple-choice questions to assess your level, clarifies your goal, researches the topic, and proposes a dependency graph for the lesson.
3. **Approve the plan.** Once you approve it, each concept follows a **motivate → establish → connect → check** teaching loop.
4. **Demonstrate understanding.** Key prerequisite concepts and the end of each topic require short answers in your own words. Programming topics also include coding tasks.
5. **Capture the lesson.** Your responses and the tutor's explanations are mirrored into a dated note. Diagrams are saved alongside the material.
6. **Review and resume.** Each checked concept becomes a review card. Use `/review` for due cards, `/status` to inspect progress, and `/checkpoint` to save your place.

## Getting started

### Requirements

- Claude Code
- Python 3
- Node.js 18 or later and npm
- Chrome or Chromium available on `PATH` for diagram verification
- Optional: `rsvg-convert`, provided by the `librsvg2-bin` package
- Optional: an Obsidian vault for lesson notes

### 1. Clone the repository

Replace the placeholder URL with this repository's clone URL:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git ~/learning
cd ~/learning
```

### 2. Install the diagram renderer

```bash
cd tools
PUPPETEER_SKIP_DOWNLOAD=1 npm install
cd ..
```

The Mermaid renderer uses your system Chrome or Chromium installation.

### 3. Configure note storage

To use Obsidian, update the following fields in `learn.config.json` to point to your vault. For example, when accessing a Windows vault from WSL:

```json
{
  "notesDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning",
  "vizDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/viz",
  "reviewsDir": "/mnt/c/Users/<you>/OneDrive/Obsidian/<vault>/learning/reviews"
}
```

Without a configured vault, `notes/` serves as the default note directory.

### 4. Set up your learner profile

Edit `LEARNER.md` with your background, goals, and learning preferences, then launch Claude Code from the project root:

```bash
claude
```

Start your first lesson with a topic of your choice:

```text
/teach Python decorators
```

## Commands

Run these commands inside Claude Code:

| Command | Purpose |
| --- | --- |
| `/teach <topic>` | Start a lesson on a new topic. |
| `/teach continue` | Resume the active lesson. |
| `/review [topic] [--limit N]` | Review due cards, optionally filtered by topic and limited in number. |
| `/code-task` | Create or check a coding exercise. |
| `/visualize <idea>` | Add a verified diagram. |
| `/status` | Show learning progress and due reviews. |
| `/checkpoint [note]` | Save the current state with an optional note. |

### Standalone scripts

You can also inspect state, reviews, and exercises directly from the terminal:

```bash
python3 scripts/state.py show
python3 scripts/srs.py stats
python3 scripts/srs.py forecast
python3 scripts/exercise.py list
```

## Project structure

| Path | Purpose |
| --- | --- |
| `.claude/settings.json` | Session model, permissions, and `SessionStart`, `Stop`, and `PreCompact` hooks. |
| `.claude/skills/` | Workflows for teaching, reviews, coding tasks, visualization, status, and checkpoints. |
| `.claude/agents/` | Researcher, Mermaid, and SVG subagent definitions. |
| `scripts/` | State management, review scheduling, exercise tooling, rendering, and hooks. |
| `state/` | Persistent state in `state.json`, review cards in `deck.json`, and progress in `progress.md`. |
| `notes/` | Default lesson notes when no vault is configured. |
| `exercises/` | Coding tasks. |
| `tools/` | Mermaid CLI dependencies; `node_modules/` is excluded from version control. |
| `learn.config.json` | Note, diagram, and review folder configuration. |
| `LEARNER.md` | Learner profile and preferences. |
| `CLAUDE.md` | Tutor instructions loaded every session. |

## Model configuration

The tutor uses the session model configured in `.claude/settings.json`:

```json
"model": "opus"
```

Use `/model` inside Claude Code to override it for the current session. Subagent models are configured separately through the `model:` field in each definition under `.claude/agents/`.
