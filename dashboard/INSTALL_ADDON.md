# Installing the dashboard-only add-on

The complete project bundle is already arranged correctly. For the smaller add-on ZIP:

1. Extract its `dashboard/` directory and launchers into your existing LearningforLunch project root, alongside `scripts/`, `LEARNER.md`, and `.claude/`. Do not replace your `scripts/`, configuration or learner state; the add-on does not contain them.
2. Add `.dashboard-local/` to your existing `.gitignore`. That directory will hold the disposable demo and local command log.
3. Run `python3 dashboard/server.py` from the project root; on Windows use `py dashboard/server.py`.
4. Open the printed localhost address. Start with Isolated demo, or switch to Live project to observe the existing checkout's saved lesson.

Alternatively, leave the add-on in a separate folder and supply the existing checkout explicitly:

```sh
python3 dashboard/server.py --project "/absolute/path/to/LearningforLunch"
```

The live view is read-only by default. The dashboard is an adapter to this project's command/data model; a substantially different future version may need adapter updates. See `README.md` for optional live controls and safety boundaries.
