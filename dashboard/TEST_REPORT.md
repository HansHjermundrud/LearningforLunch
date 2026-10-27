# Verification report

Verified on 2026-10-13 in the build environment. The implementation and test evidence are included; this is not a guarantee for every operating system or future change to the original project.

## Dashboard integration tests: 14 passed

Command:

```sh
python3 -m unittest discover -s dashboard/tests -p 'test_*.py' -v
```

Result: **14 tests passed in 29.378 seconds**, using disposable projects, notes and state. The tests verify:

- Real prepared lesson creation, exact copying of original engine source, and no copying of the personal learner profile.
- A saved pending question, separately saved answer, and later assessment.
- Prerequisite blocking after a failure while an unrelated branch remains eligible.
- The real recovery hook preserving the pending question and state revision.
- A recorded hint producing provisional readiness and a scheduling quality cap of 2.
- Independent exit evidence and the actual 1 → 6 → 15-day quality-4 review sequence.
- A later failed review changing retention without erasing coverage/readiness.
- Non-mutating live reads and refusal of live writes by default.
- Corrupt live state remaining byte-for-byte intact.
- Stale revisions being rejected inside the actual engine write lock.
- HTTP host/origin/token checks, source/path allowlisting, and snapshot export.
- Practice success not extending the schedule.
- Manual browser-style assessment respecting recorded help.
- Explicitly enabled live interaction and demo reset preserving real-project records.

The raw log is in `test-results/dashboard-tests.txt`.

## Browser interface checks: passed

The actual HTML, CSS and JavaScript were rendered in headless Chromium using Playwright. Checks covered all 14 guided steps through visible controls, graph colors/branch blocking, recovery output, hint caps, review cards, evidence ledger, source-code dialog, switching to empty read-only live state, responsive layout at 390 px, and presentation layout. No JavaScript page errors were reported. Desktop and mobile layouts were inspected from screenshots.

**Environment limitation:** the installed browser's managed policy blocks all URL navigation, including localhost. Therefore the actual application files were rendered in `about:blank`, with `fetch` bridged through the test harness to the running local HTTP server. No application source was changed to make those tests pass. The HTTP server and API were also tested directly. These checks are not a claim that native localhost navigation was tested in that restricted browser.

The raw interface-check log is in `test-results/browser-checks.txt`. A screenshot from the working interface is included as `PREVIEW.png`.

## Original project regression suite: 56 passed, 1 inherited failure

Command (original suite and Python engine files unchanged):

```sh
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
```

Result: **57 tests ran in 370.784 seconds; one failed**:

```text
test_selftest_never_touches_absolute_configured_paths
scripts/selftest.sh: line 6: set: pipefail\r: invalid option name
```

The uploaded `scripts/selftest.sh` contains Windows CRLF line endings. Its isolation regression calls it using Bash in this Linux environment, where the trailing carriage return prevents that shell runner from starting. This failure predates the dashboard. The original shell runner is preserved, not silently repaired. All other original regression tests passed. An existing unclosed-file ResourceWarning was also printed by that suite; it was not a test failure.

The raw log is in `test-results/original-regression.txt`.

## Integrity and platform scope

All original `scripts/*.py` files are byte-for-byte identical to those in the uploaded archive. The original engine's teaching, grading, prerequisite, storage and scheduling logic was not edited.

The dashboard additions, launchers and documentation are new. `.gitignore` adds the private dashboard runtime directory. The provided Windows and macOS launchers were not executed on those operating systems; the server and workflows were exercised in Linux/Python 3.13 with Chromium interface rendering. The code targets the original project's Python 3.10+ requirement, but it was not separately run under each supported Python version.

No model/API calls, actual learner documents or personal learner records were used in the demonstration tests. No live Claude Code tutoring session was started as part of testing.
