# Learning Observatory — local presentation dashboard

A browser-based presentation and inspection layer for **this LearningforLunch project**. It runs the existing Python engine, rather than reimplementing its learning rules or substituting a generic AI demo.

## Start

From the project folder:

```sh
python3 dashboard/server.py
```

On Windows:

```powershell
py dashboard/server.py
```

The server opens **http://localhost:8765**. Keep its terminal open. Stop with **Ctrl+C**. Python **3.10 or newer** is required. There are no pip/npm dependencies for the dashboard, no CDN requests, and no model/API key requirement for the demonstration.

Convenience launchers are included in the project root: `Start dashboard.bat`, `Start dashboard.command`, and `start_dashboard.sh`. The terminal command is the most portable option. On macOS, a downloaded `.command` launcher may require executable permission; the terminal command does not.

This is a local web application, not a self-contained HTML file. Opening `dashboard/static/index.html` with a `file://` URL will not connect it to the Python engine.

## Two genuinely different modes

### Isolated demo (default)

The dashboard copies the project's original Python scripts to `.dashboard-local/demo/scripts/` and writes a separate, explicitly sandboxed configuration. It does **not** copy personal state, lesson notes, resources, exercise submissions, or the learner profile. It loads a fictional fractions lesson from `dashboard/demo_data.py` through the real `start`, `plan-set`, `prep-topic`, `prep-node`, and `plan-approve` commands.

The demonstration then executes the same command implementations used by a normal lesson. Questions, attempts, prerequisites, review cards and schedules are real persisted engine state. Sample learner answers and sample assessments are **prepared inputs**, not model-generated evaluations. No Claude process or other model is launched.

The demo clock is injected using the engine's existing `LEARN_NOW` environment variable. Advancing it changes only the demo subprocess clock, not your operating-system clock or live-project records. The clock starts at the actual local date when the sandbox is first created. The saved demo and clock survive dashboard restarts; Reset starts fresh.

Reset removes only the marked `.dashboard-local/demo/` directory, then prepares a new demo. It does not reset your actual `state/` or notes. Do not run a genuine lesson inside the demo directory.

### Live project (read-only by default)

The live view observes the checkout passed as `--project`. To observe your existing checkout rather than the newly extracted bundle:

```sh
python3 dashboard/server.py --project "/absolute/path/to/your/LearningforLunch"
```

Run Claude Code in **that same checkout**, use its normal `/teach` or `/review` workflow, and keep the dashboard's Live project view open. It polls saved state approximately every 1.5 seconds when the browser tab is visible. Updates occur after engine commands save changes. A fresh checkout with no learner state correctly shows an empty live view.

Live reading uses `learnlib.Store(write=False)`. It intentionally avoids `load_state()` and `load_deck()`, because those helpers may recover a journal and write files. If a commit is in progress or an interrupted journal needs recovery, the dashboard reports the condition and retries. It does **not** repair or overwrite the live files. The previous good view may remain visible with an error indicator until the issue is resolved through the project's normal tools.

### Optional browser control of the real project

Live project mutation is off by default. Enable it deliberately at launch:

```sh
python3 dashboard/server.py --project "/path/to/LearningforLunch" --enable-live-controls
```

This enables the prepared-question, answer, hint, explicit assessment and review-grade controls. Every live browser action asks for confirmation. Reset, simulated time and recovery-hook demonstrations remain demo-only.

The presenter supplies the semantic assessment. Required points are selected explicitly before recording a pass; the original engine applies its caps and readiness rules. The dashboard is **not** an AI grading service.

Writes use the original engine's Store lock. The adapter checks the expected state revision **inside that lock**, preventing a stale browser from acting on a lesson that has changed. Coordinate with Claude and avoid submitting the same assessment in two places. A browser answer is saved for Claude to read on a subsequent interaction; this dashboard does not inject a new message into an already-running Claude conversation.

## What each screen shows

| Screen | Function |
|---|---|
| **Live classroom** | Guided story, pending question, prerequisite graph, coverage/readiness/retention, selected concept preparation, last action and field changes. |
| **Evidence ledger** | Separate evidence fields for every concept; saved lesson attempts, assistance and quality; read-only raw state inspection. |
| **Review lab** | Real card intervals, due dates, ease, repetition/lapse counts and review history. Advance only demo time and submit explicit review/practice/repair assessments. |
| **How it works** | The actual Claude → Python rules → persistent files architecture, with implementation links and important limits. |
| **Engine trace** | Dashboard command equivalents, stdin payloads, real output and before/after field changes; saved project log milestones; recovery-hook output; JSON export. |

Click a graph concept to inspect it. Click **View implementation** to open the actual source with line numbers and a SHA-256 fingerprint. Inspection is read-only.

Exports contain answers, answer keys and local paths. Treat a live export as personal learning data; inspect it before sharing.

## Presenting

Use **Begin walkthrough**, followed by **Next step**. The fourteen steps cover:

1. Persist a question before waiting.
2. Save an answer separately from its assessment.
3. Record an independent pass and create a review card.
4. Ask a concept with a satisfied prerequisite.
5. Record a misconception and block the dependent branch.
6. Continue an unrelated eligible branch.
7. Ask a repair check and record a hint.
8. Execute the actual SessionStart hook to recover the pending interaction.
9. Observe an assisted pass: provisional readiness and quality capped at 2.
10. Apply the concept in addition.
11. Meet the independent exit criterion and finish.
12. Advance one demo day: a successful due review changes 1 day to 6 days.
13. Advance six more demo days: another quality-4 review changes 6 to 15 days.
14. Fail a later review: retention needs review, while coverage/readiness remain intact.

Manual actions pause the guided sequence because its prepared assumptions may no longer hold. Reset the isolated demo to replay the story. The project’s actual formulas and policies are never reset or edited by the presentation.

**Keyboard:** `F` toggles the presentation layout; Right Arrow advances the story on the classroom screen when not typing; Escape closes a dialog or leaves presentation layout. The toolbar also has a presentation-layout button. **Show speaker notes** reveals a sentence for the current step. See `PRESENTER_NOTES.md` for a compact script.

## Honest boundaries

- Claude still handles teaching and meaning-based assessment in a real lesson. This dashboard does not embed or call Claude.
- The phase ribbon is an interpretation of saved fields. Guided-demo phases are explicitly presentation annotations. It does not track unsaved prose, token generation, subagent work, or hidden model reasoning.
- A trace entry shows the **equivalent original CLI command**. The adapter actually starts a fresh `bridge.py` process, imports the unmodified module and calls its existing `main(argv)` entry point, with JSON supplied on stdin. The displayed elapsed time includes adapter/snapshot overhead, not just computation inside the rule.
- Graph eligibility is computed by the actual `state.eligible()` function, not by JavaScript. The browser only lays out and colors its results.
- There is no new RAG or vector-database layer. Document support in this project uses registered sources and digests for preparation.
- The project does not implement model-weight training. Adaptation uses recorded evidence, preparation and teaching instructions.
- The supplied implementation allows an unassisted repair pass to become `ready`, while the teaching policy describes a more conservative approach. The dashboard does not silently fix or conceal this. The guided repair includes a real recorded hint and therefore becomes provisional under the existing code.
- `srs.py grade` stores review history in the deck; it does not create a `state.py record` lesson attempt. Both are shown in their respective screens.
- Code exercises are explained in the architecture view, but this dashboard does not add an exercise editor or execute arbitrary browser-submitted code.
- The demo review dates are synthetic after clock advancement; they are labeled as demo time. The 1 → 6 → 15 sequence is an observed result for the guided quality-4 sequence, not a universal interval schedule.

## Files added

```text
dashboard/
  server.py                 Loopback HTTP server and allowlisted action routing
  bridge.py                 Process-isolated adapter to original modules
  demo_data.py              Prepared sample lesson and narration
  static/index.html         Browser shell
  static/style.css          Responsive presentation styling
  static/app.js             Live views, controls and source inspector
  tests/test_dashboard.py   Standard-library integration/security tests
  README.md
  PRESENTER_NOTES.md
```

No original `scripts/*.py` files are changed. Runtime files are isolated under `.dashboard-local/` by default:

```text
.dashboard-local/
  demo/                     Disposable script copy, config, state and notes
  presentation.json         Demo clock and guided-story position
  commands.jsonl            Local dashboard command audit log
```

Use `--data-dir "/some/separate/folder"` to change the runtime location. Keep this directory out of version control; the bundle adds it to `.gitignore`. Do not share runtime files without checking their contents. Do not point two dashboard instances at the same data directory; each instance should have its own `--data-dir`.

## Local security

The server binds to `127.0.0.1` only. It is intended for a trusted personal computer, not Internet deployment or a classroom multi-user server. There are no CDN assets or external network calls from the dashboard. Host validation, same-origin checks, a per-run request token, a restricted static/source allowlist and a restrictive content-security policy reduce unintended browser access. There is no arbitrary-shell or arbitrary-path endpoint.

This is not an authentication system against other processes or users already on your computer. Do not expose it through port forwarding, tunnels or a public interface.

## Troubleshooting

**Port already in use:** run `python3 dashboard/server.py --port 8766` and use the address it prints.

**Browser did not open:** paste the printed `http://localhost:PORT` address into a browser. `http://127.0.0.1:PORT` also works.

**Module/state errors:** the browser surfaces the actual engine error. Verify `--project` points at a complete checkout containing `scripts/state.py`, `srs.py`, and `learnlib.py`. Corrupt live state is not replaced with empty state.

**Live controls disabled:** this is the default safety setting. The isolated demo is fully interactive without enabling live writes.

**Lesson changed:** a concurrent engine command made the browser's state stale. Refresh and inspect the question before trying again.

**Timezone:** the engine uses its configured timezone where IANA zone data is available and otherwise its existing local-time fallback. This is inherited from the original engine; the dashboard does not replace its clock implementation.

**Demo does not match a recently edited script:** Reset the isolated demo to copy the checkout's current Python scripts again. Your actual learner records remain unchanged.

## Tests

From the project root:

```sh
python3 -m unittest discover -s dashboard/tests -p "test_*.py" -v
```

The dashboard tests create disposable projects and do not touch your configured state or vault. The original project's separate suite is:

```sh
python3 -m unittest discover -s scripts/tests -p "test_*.py"
```

`TEST_REPORT.md` in the bundle records what was actually checked during creation, including the browser-testing environment limitation.
