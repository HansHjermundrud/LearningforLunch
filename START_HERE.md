# Open the interactive LearningforLunch dashboard

From this folder:

```sh
python3 dashboard/server.py
```

Windows: `py dashboard/server.py`, or double-click **Start dashboard.bat**.

Open **http://localhost:8765** if the browser does not open automatically. Keep the terminal running. Python 3.10+ is required; no extra packages or model key are needed for the demo.

Choose **Isolated demo → Begin walkthrough → Next step**. The prepared story runs actual project commands and demonstrates prerequisite gating, recorded hints, persistent questions, separate evidence fields and adaptive review scheduling.

Use **F** for presentation layout and **Show speaker notes** for narration. The project’s original Python engine has not been modified. The demo's answers and assessments are explicitly prepared examples, not live AI grading.

To observe the checkout you actually teach with:

```sh
python3 dashboard/server.py --project "/path/to/your/existing/LearningforLunch"
```

Switch to **Live project**, then continue the lesson in Claude Code in that same checkout. Live mode is read-only unless you deliberately launch with `--enable-live-controls`.

See **dashboard/README.md** for setup, boundaries and troubleshooting; **dashboard/PRESENTER_NOTES.md** for a presentation script; **dashboard/TEST_REPORT.md** for verification results.
