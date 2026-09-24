#!/usr/bin/env python3
"""Coding exercises for the learning system.

Each exercise is a folder under exercisesDir/<topic>/<name>/ with:
  README.md        the task (written by the teacher)
  <starter file>   what the learner edits
  <test file>      tests the teacher writes (visible to the learner)
  check.sh         runs the tests; exit code 0 = pass

Usage (from the repo root):
  python3 scripts/exercise.py new --topic SLUG --name NAME --lang python|js|other [--title "..."]
  python3 scripts/exercise.py check DIR
  python3 scripts/exercise.py list
"""
from __future__ import annotations

import argparse
import os
import pathlib
import stat
import subprocess
import sys

import learnlib as L

TEMPLATES = {
    "python": {
        "starter": ("solution.py", '"""Write your solution here. Keep the function name; the tests import it."""\n\n\ndef solve(*args, **kwargs):\n    raise NotImplementedError\n'),
        "test": ("test_solution.py", "import unittest\n\nfrom solution import solve\n\n\nclass TestSolution(unittest.TestCase):\n    def test_example(self):\n        # The teacher replaces this with real cases from the README.\n        self.assertEqual(solve(), None)\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n"),
        "check": "#!/usr/bin/env bash\nset -u\ncd \"$(dirname \"$0\")\"\npython3 -m unittest -q test_solution.py\n",
    },
    "js": {
        "starter": ("solution.js", "// Write your solution here. Keep the export name; the tests import it.\n\nfunction solve() {\n  throw new Error('not implemented');\n}\n\nmodule.exports = { solve };\n"),
        "test": ("solution.test.js", "const test = require('node:test');\nconst assert = require('node:assert/strict');\nconst { solve } = require('./solution');\n\ntest('example', () => {\n  // The teacher replaces this with real cases from the README.\n  assert.equal(solve(), undefined);\n});\n"),
        "check": "#!/usr/bin/env bash\nset -u\ncd \"$(dirname \"$0\")\"\nnode --test solution.test.js\n",
    },
    "other": {
        "starter": ("solution.txt", "Replace this file with the starter for the chosen language.\n"),
        "test": ("TESTS.md", "Describe how the solution is checked, or replace check.sh with a real test runner.\n"),
        "check": "#!/usr/bin/env bash\nset -u\ncd \"$(dirname \"$0\")\"\necho 'No automatic check defined for this exercise yet.'\nexit 1\n",
    },
}


def readme(title: str, topic: str, lang: str, starter: str, test: str) -> str:
    return (
        f"---\ntitle: \"{title}\"\ndate: {L.today()}\ntopic: {topic}\nlang: {lang}\nstatus: open\n---\n"
        f"# {title}\n\n"
        f"_Created {L.today()} · topic `{topic}` · language {lang}_\n\n"
        "## Task\n\n(The teacher writes the task here: what to build, inputs, outputs, constraints.)\n\n"
        "## Examples\n\n```\ninput  -> output\n```\n\n"
        "## How to work\n\n"
        f"1. Edit `{starter}`.\n"
        f"2. Run `bash check.sh` in this folder (tests are in `{test}`).\n"
        "3. Tell the teacher \"done\" (or ask for a hint) in the chat.\n\n"
        "## Result\n\n(Filled in by the teacher after review: date, passed/failed, feedback, grade 0-5.)\n"
    )


def cmd_new(args, root: pathlib.Path):
    lang = args.lang if args.lang in TEMPLATES else "other"
    folder = root / L.slugify(args.topic) / L.slugify(args.name)
    if folder.exists():
        sys.exit(f"error: {folder} already exists")
    folder.mkdir(parents=True)
    tpl = TEMPLATES[lang]
    starter_name, starter_body = tpl["starter"]
    test_name, test_body = tpl["test"]
    (folder / starter_name).write_text(starter_body, "utf-8")
    (folder / test_name).write_text(test_body, "utf-8")
    check = folder / "check.sh"
    check.write_text(tpl["check"], "utf-8")
    check.chmod(check.stat().st_mode | stat.S_IXUSR)
    (folder / "README.md").write_text(readme(args.title or args.name, args.topic, lang, starter_name, test_name), "utf-8")
    print(f"Created exercise at {L.rel(folder)}\n  task:    README.md (write the task and examples)\n  starter: {starter_name}\n  tests:   {test_name} (write real cases)\n  check:   bash {L.rel(check)}")


def cmd_check(args, root: pathlib.Path):
    folder = L.resolve(args.dir)
    check = folder / "check.sh"
    if not check.exists():
        sys.exit(f"error: no check.sh in {folder}")
    res = subprocess.run(["bash", str(check)], capture_output=True, text=True, timeout=300, check=False)
    output = (res.stdout + res.stderr).strip()
    tail = "\n".join(output.splitlines()[-40:])
    verdict = "PASS" if res.returncode == 0 else f"FAIL (exit {res.returncode})"
    print(f"{verdict} · {L.rel(folder)} · {L.fmt_local(L.ts())}\n{tail}")
    sys.exit(0 if res.returncode == 0 else 1)


def cmd_list(args, root: pathlib.Path):
    found = sorted(p.parent for p in root.glob("*/*/README.md"))
    if not found:
        print("No exercises yet.")
    for folder in found:
        status = "?"
        try:
            for line in (folder / "README.md").read_text("utf-8").splitlines()[:12]:
                if line.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
        except Exception:  # noqa: BLE001
            pass
        print(f"{status:8} {L.rel(folder)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("--topic", required=True); p.add_argument("--name", required=True)
    p.add_argument("--lang", default="python"); p.add_argument("--title"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("check"); p.add_argument("dir"); p.set_defaults(fn=cmd_check)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    args = parser.parse_args(argv)
    args.fn(args, L.dir_path("exercisesDir", create=True))


if __name__ == "__main__":
    main()
