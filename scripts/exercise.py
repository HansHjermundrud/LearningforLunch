#!/usr/bin/env python3
"""Coding exercises for the learning system.

Each exercise is a folder under exercisesDir/<topic>/<name>/ with:
  README.md          the task (written by the teacher from the prepared spec)
  <starter file>     what the learner edits (never contains the solution)
  <test file>        tests the teacher writes (visible to the learner)
  check.sh [FILE]    runs the tests against FILE (default: the starter); exit 0 = pass
  .reference/        reference solution and deliberately flawed variants + expect.json
                     (preparation only: never shown to the learner)
  .attempts/         copies of every checked file, so retries never overwrite history

Languages: python, js, c (C with OpenMP: gcc -O2 -Wall -Wextra -fopenmp, several
sizes and thread counts, a serial oracle, tolerances, a timeout, an optional
perf.sh that is not part of the grade).

Usage (from the repo root):
  python3 scripts/exercise.py env                        # compiler / OpenMP availability
  python3 scripts/exercise.py new --topic SLUG --name NAME --lang python|js|c|other [--title "..."]
  python3 scripts/exercise.py check DIR [--file retry.c] [--timeout SEC]
  python3 scripts/exercise.py validate DIR               # reference passes, flawed variants fail
  python3 scripts/exercise.py list
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import stat
import subprocess
import sys

import learnlib as L

C_STARTER = r'''#include <omp.h>
#include <stddef.h>

/*
 * Task: see README.md. Implement the function below with OpenMP.
 * Keep the signature: test_main.c calls it and compares against a serial oracle.
 * Do not edit test_main.c. Run `bash check.sh` in this folder.
 */
double solve(const double *a, size_t n)
{
    (void)a;
    (void)n;
    return 0.0; /* TODO */
}
'''

C_TEST = r'''#include <math.h>
#include <omp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

double solve(const double *a, size_t n);

/* Serial oracle: the teacher writes the sequential answer here. */
static double oracle(const double *a, size_t n)
{
    double s = 0.0;
    for (size_t i = 0; i < n; i++) s += a[i];
    return s;
}

static int check(size_t n, int threads, int run, double tol)
{
    double *a = malloc((n ? n : 1) * sizeof *a);
    if (!a) { printf("FAIL: malloc\n"); return 1; }
    for (size_t i = 0; i < n; i++) a[i] = (double)(i % 97) * 0.5 - 7.25;
    omp_set_num_threads(threads);
    double want = oracle(a, n);
    double got = solve(a, n);
    free(a);
    double diff = fabs(got - want);
    double allowed = tol * (1.0 + fabs(want));
    if (!(diff <= allowed)) {
        printf("FAIL n=%zu threads=%d run=%d: got %.10g, expected %.10g (|diff| %.3g > %.3g)\n",
               n, threads, run, got, want, diff, allowed);
        return 1;
    }
    return 0;
}

int main(void)
{
    const size_t sizes[] = {0, 1, 7, 1000, 100003, 2000000};
    const int threads[] = {1, 2, 3, 8};
    const double tol = 1e-9; /* relative + absolute; floating-point sums may differ in the last bits */
    int fails = 0, runs = 0;
    for (size_t s = 0; s < sizeof sizes / sizeof *sizes; s++)
        for (size_t t = 0; t < sizeof threads / sizeof *threads; t++)
            for (int run = 0; run < 5; run++) {
                runs++;
                if (check(sizes[s], threads[t], run, tol)) { fails++; if (fails >= 3) goto done; }
            }
done:
    if (fails) { printf("FAIL: %d of %d runs failed\n", fails, runs); return 1; }
    printf("PASS: %d runs over %zu sizes and %zu thread counts (tolerance %.0e)\n",
           runs, sizeof sizes / sizeof *sizes, sizeof threads / sizeof *threads, tol);
    printf("NOTE: passing runs do not prove the absence of a data race; explain the synchronization in your answer.\n");
    return 0;
}
'''

C_CHECK = r'''#!/usr/bin/env bash
# Usage: bash check.sh [FILE]   (FILE defaults to solution.c; use it for retries, e.g. retry-2026-10-01.c)
set -u
cd "$(dirname "$0")"
file="${1:-solution.c}"
timeout_s="${CHECK_TIMEOUT:-60}"
if [ ! -f "$file" ]; then echo "FAIL: no such file $file"; exit 2; fi
CC="${CC:-gcc}"
if ! command -v "$CC" >/dev/null 2>&1; then
    echo "FAIL: compiler '$CC' not found. Install gcc (Ubuntu: sudo apt install build-essential) or set CC."; exit 3
fi
if ! echo 'int main(void){return 0;}' | "$CC" -fopenmp -x c - -o /dev/null 2>/dev/null; then
    echo "FAIL: '$CC' cannot build with -fopenmp (libgomp missing?). Ubuntu: sudo apt install gcc libgomp1"; exit 3
fi
if grep -q '__SOLUTION_MARKER__' test_main.c 2>/dev/null; then echo "FAIL: test_main.c still has the template marker"; exit 2; fi
if ! "$CC" -std=c11 -O2 -Wall -Wextra -fopenmp "$file" test_main.c -lm -o .test_bin 2>.build.log; then
    echo "FAIL: does not compile:"; grep -E 'error|warning' .build.log | head -20; exit 1
fi
if grep -q 'warning' .build.log; then echo "warnings:"; grep -E 'warning' .build.log | head -10; fi
if command -v timeout >/dev/null 2>&1; then
    timeout "$timeout_s" ./.test_bin; rc=$?
    if [ $rc -eq 124 ]; then echo "FAIL: timed out after ${timeout_s}s (deadlock, livelock or far too slow?)"; fi
else
    ./.test_bin; rc=$?
fi
exit $rc
'''

C_PERF = r'''#!/usr/bin/env bash
# Optional performance experiment. NOT part of the grade: timings are noisy and a
# correct solution is not "wrong" because a run was slow. Compare threads=1 vs more.
set -u
cd "$(dirname "$0")"
file="${1:-solution.c}"
gcc -std=c11 -O2 -Wall -fopenmp "$file" test_main.c -lm -o .perf_bin || exit 1
for t in 1 2 4 8; do
    printf "threads=%d  " "$t"
    OMP_NUM_THREADS=$t /usr/bin/env time -f "%es elapsed" ./.perf_bin >/dev/null 2>.perf_time; tail -1 .perf_time
done
'''

C_REFERENCE = r'''#include <omp.h>
#include <stddef.h>

/* Reference solution (preparation only; never shown to the learner). */
double solve(const double *a, size_t n)
{
    double s = 0.0;
    #pragma omp parallel for reduction(+:s)
    for (size_t i = 0; i < n; i++) s += a[i];
    return s;
}
'''

C_FLAWED_OFFBYONE = r'''#include <omp.h>
#include <stddef.h>

/* Deliberately wrong: skips the last element. Must FAIL deterministically. */
double solve(const double *a, size_t n)
{
    double s = 0.0;
    if (n == 0) return 0.0;
    #pragma omp parallel for reduction(+:s)
    for (size_t i = 0; i + 1 < n; i++) s += a[i];
    return s;
}
'''

C_FLAWED_RACE = r'''#include <omp.h>
#include <stddef.h>

/* Deliberately racy: shared accumulator, no reduction. Usually FAILS on 2+ threads
   with large n, but a passing run proves nothing (expect.json marks it "unreliable"). */
double solve(const double *a, size_t n)
{
    double s = 0.0;
    #pragma omp parallel for
    for (size_t i = 0; i < n; i++) s += a[i];
    return s;
}
'''

C_EXPECT = {
    "reference.c": "PASS",
    "flawed-offbyone.c": "FAIL",
    "flawed-race.c": "FAIL-or-unreliable",
    "_note": "FAIL-or-unreliable: a racy program may pass by luck; validate reports it and the grader must require reasoning about synchronization.",
}

TEMPLATES = {
    "python": {
        "starter": ("solution.py", '"""Write your solution here. Keep the function name; the tests import it."""\n\n\ndef solve(*args, **kwargs):\n    raise NotImplementedError\n'),
        "test": ("test_solution.py", "import importlib\nimport os\nimport unittest\n\nsolution = importlib.import_module(os.environ.get('SOLUTION_MODULE', 'solution'))\nsolve = solution.solve\n\n\nclass TestSolution(unittest.TestCase):\n    def test_example(self):\n        # The teacher replaces this with real cases from the README.\n        self.assertEqual(solve(), None)\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n"),
        "check": "#!/usr/bin/env bash\n# Usage: bash check.sh [FILE.py]  (a retry file is imported instead of solution.py)\nset -u\ncd \"$(dirname \"$0\")\"\nfile=\"${1:-solution.py}\"\nSOLUTION_MODULE=\"${file%.py}\" python3 -m unittest -q test_solution.py\n",
    },
    "js": {
        "starter": ("solution.js", "// Write your solution here. Keep the export name; the tests import it.\n\nfunction solve() {\n  throw new Error('not implemented');\n}\n\nmodule.exports = { solve };\n"),
        "test": ("solution.test.js", "const test = require('node:test');\nconst assert = require('node:assert/strict');\nconst { solve } = require('./' + (process.env.SOLUTION_FILE || 'solution.js'));\n\ntest('example', () => {\n  // The teacher replaces this with real cases from the README.\n  assert.equal(solve(), undefined);\n});\n"),
        "check": "#!/usr/bin/env bash\n# Usage: bash check.sh [FILE.js]\nset -u\ncd \"$(dirname \"$0\")\"\nSOLUTION_FILE=\"${1:-solution.js}\" node --test solution.test.js\n",
    },
    "c": {
        "starter": ("solution.c", C_STARTER),
        "test": ("test_main.c", C_TEST),
        "check": C_CHECK,
        "extra": {"perf.sh": C_PERF, ".reference/reference.c": C_REFERENCE, ".reference/flawed-offbyone.c": C_FLAWED_OFFBYONE,
                  ".reference/flawed-race.c": C_FLAWED_RACE, ".reference/expect.json": json.dumps(C_EXPECT, indent=2) + "\n",
                  ".gitignore": ".test_bin\n.perf_bin\n.build.log\n.perf_time\n.validate/\n"},
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
        "## Task\n\n(The teacher writes the task here: what to build, inputs, outputs, constraints, which node it exercises.)\n\n"
        "## Examples\n\n```\ninput  -> output\n```\n\n"
        "## How to work\n\n"
        f"1. Edit `{starter}`.\n"
        f"2. Run `bash check.sh` in this folder (tests are in `{test}`).\n"
        "3. Tell the teacher \"done\" (or ask for a hint) in the chat.\n"
        + ("4. Optional, not graded: `bash perf.sh` compares thread counts.\n" if lang == "c" else "")
        + "\n## Result\n\n(Filled in by the teacher after review: date, passed/failed, feedback, grade 0-5.)\n"
    )


def cmd_env(args, root):
    cc = shutil.which("gcc") or shutil.which("cc")
    if not cc:
        print("C: no gcc/cc on PATH. Ubuntu: sudo apt install build-essential")
    else:
        ver = subprocess.run([cc, "--version"], capture_output=True, text=True, check=False).stdout.splitlines()[:1]
        probe = subprocess.run([cc, "-fopenmp", "-x", "c", "-", "-o", "/dev/null"], input="int main(void){return 0;}",
                               capture_output=True, text=True, check=False)
        if probe.returncode == 0:
            macro = subprocess.run([cc, "-fopenmp", "-dM", "-E", "-x", "c", "-"], input="", capture_output=True, text=True, check=False).stdout
            omp = next((l.split()[-1] for l in macro.splitlines() if "_OPENMP" in l), "?")
            print(f"C: {cc} ({ver[0] if ver else '?'}) with -fopenmp OK (_OPENMP {omp})")
        else:
            print(f"C: {cc} found but -fopenmp fails: {probe.stderr.strip().splitlines()[-1] if probe.stderr else 'unknown error'}. Ubuntu: sudo apt install libgomp1")
    for name, cmd in (("python", ["python3", "--version"]), ("node", ["node", "--version"])):
        path = shutil.which(cmd[0])
        print(f"{name}: " + (subprocess.run(cmd, capture_output=True, text=True, check=False).stdout.strip() if path else "not found"))


def cmd_new(args, root: pathlib.Path):
    lang = args.lang if args.lang in TEMPLATES else "other"
    folder = root / L.slugify(args.topic) / L.slugify(args.name)
    if folder.exists():
        raise L.LearnError(f"{folder} already exists")
    folder.mkdir(parents=True)
    tpl = TEMPLATES[lang]
    starter_name, starter_body = tpl["starter"]
    test_name, test_body = tpl["test"]
    (folder / starter_name).write_text(starter_body, "utf-8")
    (folder / test_name).write_text(test_body, "utf-8")
    check = folder / "check.sh"
    check.write_text(tpl["check"], "utf-8")
    check.chmod(check.stat().st_mode | stat.S_IXUSR)
    for name, body in tpl.get("extra", {}).items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, "utf-8")
        if name.endswith(".sh"):
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
    (folder / "README.md").write_text(readme(args.title or args.name, args.topic, lang, starter_name, test_name), "utf-8")
    print(f"Created exercise at {L.rel(folder)}\n  task:    README.md (write the task and examples)\n  starter: {starter_name}\n  tests:   {test_name} (write real cases)\n  check:   bash {L.rel(check)} [retry-file]")
    if lang == "c":
        print("  prep:    .reference/ holds reference.c + flawed variants; run `exercise.py validate` before handing out")


def _run_check(folder: pathlib.Path, file: str | None, timeout: int) -> tuple[int, str]:
    check = folder / "check.sh"
    if not check.exists():
        raise L.LearnError(f"no check.sh in {folder}")
    cmd = ["bash", str(check)] + ([file] if file else [])
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env={**__import__("os").environ, "CHECK_TIMEOUT": str(timeout)})
    except subprocess.TimeoutExpired:
        return 124, f"FAIL: check.sh exceeded {timeout}s"
    output = (res.stdout + res.stderr).strip()
    return res.returncode, output


def cmd_check(args, root: pathlib.Path):
    folder = L.resolve(args.dir)
    file = args.file
    if file:
        fpath = folder / file
        if not fpath.exists():
            raise L.LearnError(f"retry file {fpath} does not exist")
        if fpath.resolve().parent != folder.resolve():
            raise L.LearnError("the retry file must live inside the exercise folder")
    rc, output = _run_check(folder, file, args.timeout)
    tail = "\n".join(output.splitlines()[-40:])
    verdict = "PASS" if rc == 0 else f"FAIL (exit {rc})"
    # keep a copy of what was checked, so later retries never lose an earlier attempt
    checked = folder / (file or _starter_name(folder))
    if checked.exists():
        attempts = folder / ".attempts"
        attempts.mkdir(exist_ok=True)
        stamp = L.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(checked, attempts / f"{stamp}-{'PASS' if rc == 0 else 'FAIL'}-{checked.name}")
    print(f"{verdict} · {L.rel(folder)} · file {checked.name} · {L.fmt_local(L.ts())}\n{tail}")
    sys.exit(0 if rc == 0 else 1)


def _starter_name(folder: pathlib.Path) -> str:
    for cand in ("solution.c", "solution.py", "solution.js", "solution.txt"):
        if (folder / cand).exists():
            return cand
    return "solution"


def cmd_validate(args, root: pathlib.Path):
    """Preparation step: the reference must pass and each flawed variant must fail."""
    folder = L.resolve(args.dir)
    ref_dir = folder / ".reference"
    expect = L.read_json(ref_dir / "expect.json", None)
    if not expect:
        raise L.LearnError(f"no {L.rel(ref_dir / 'expect.json')}: add reference/flawed files and their expected verdicts")
    problems = 0
    for name, want in expect.items():
        if name.startswith("_"):
            continue
        src = ref_dir / name
        if not src.exists():
            print(f"MISSING {name}")
            problems += 1
            continue
        work = folder / ".validate"
        work.mkdir(exist_ok=True)
        tmp = folder / f".validate-{name}"
        shutil.copy2(src, tmp)
        try:
            rc, output = _run_check(folder, tmp.name, args.timeout)
        finally:
            tmp.unlink(missing_ok=True)
        got = "PASS" if rc == 0 else "FAIL"
        if want == "FAIL-or-unreliable":
            ok = True
            note = "" if got == "FAIL" else " (passed by luck: this test cannot catch the race; grade the reasoning)"
        else:
            ok = got == want
            note = ""
        print(f"{'ok  ' if ok else 'BAD '} {name}: expected {want}, got {got}{note}")
        if not ok:
            problems += 1
            print("      " + "\n      ".join(output.splitlines()[-5:]))
        shutil.rmtree(work, ignore_errors=True)
    for stray in folder.glob(".attempts/*validate*"):
        stray.unlink()
    if problems:
        raise L.LearnError(f"{problems} validation problem(s); do not hand this exercise out yet")
    print("exercise validated: reference passes, flawed variants behave as expected")


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
        attempts = len(list((folder / ".attempts").glob("*"))) if (folder / ".attempts").exists() else 0
        print(f"{status:8} {L.rel(folder)}" + (f"  ({attempts} checked attempt(s))" if attempts else ""))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("env").set_defaults(fn=cmd_env)
    p = sub.add_parser("new"); p.add_argument("--topic", required=True); p.add_argument("--name", required=True)
    p.add_argument("--lang", default="python"); p.add_argument("--title"); p.set_defaults(fn=cmd_new)
    p = sub.add_parser("check"); p.add_argument("dir"); p.add_argument("--file"); p.add_argument("--timeout", type=int, default=120); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("validate"); p.add_argument("dir"); p.add_argument("--timeout", type=int, default=120); p.set_defaults(fn=cmd_validate)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    args = parser.parse_args(argv)
    L.cli_main(lambda: args.fn(args, L.dir_path("exercisesDir", create=True)))


if __name__ == "__main__":
    main()
