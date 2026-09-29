# How the learning system works (v2)

This is the reference for the data, the commands, and what runs when. The skills
under `.claude/skills/` tell the teacher *how to teach*; this file says what the
scripts guarantee. Everything is standard-library Python 3.

## Preparation versus teaching

| Stage | What runs | Cost |
|---|---|---|
| Planning a topic | Researcher in 1-2 batched calls; `prep-topic`; `plan-set`; `prep-node` for the upcoming chunk; `exercise.py new` + `validate`; `state.py validate` | Heavy, once; extended at chunk boundaries |
| A learner-supplied document | `source-add` (hash, page count); `document-reader` subagent reads the requested pages once and writes a digest; `source-digest`; flagged conflicts to the researcher; plan adjusted with `node-add`/`node-edit`/`scope` | Heavy, once per document version |
| Teaching a prepared node | `prep-show` (read), teach, `ask`, wait | No research, no subagent, no diagram, no map |
| An answer turn | `record < result.json` | One local command: attempt + readiness + card + NEXT |
| Recovery after compaction or restart | SessionStart hook injects a ~12-line snapshot; `pending` shows the open question | No transcript reading, no card dump |
| A question outside the prepared material | Answer from established knowledge; verify a genuinely uncertain claim narrowly with the researcher; add the result to the prep | Bounded |

## Files

| Path | Content |
|---|---|
| `state/state.json` | Topics: goal, edge, plan nodes with evidence fields, attempts, the pending interaction, topic-level preparation, log. Schema version 2. |
| `state/deck.json` | Review cards (SM-2 fields, history, variants, key versions). Schema version 2. |
| `state/prep/<topic>/<node>.json` | Prepared material per node (objective, outline, claims, misconceptions, checks with keys and hints, exercise spec). |
| `state/prep/<topic>/sources/<id>.json` | Digest of a local document: summary, objectives, sections with pages and depth, assumed prerequisites, node map, flagged conflicts; the file hash it was made from. |
| `resources/` | The documents themselves (`resourcesDir`). Gitignored except its README. |
| `state/progress.md` | Human-readable mirror of the state, rewritten on every save. |
| `state/backups/*.bak` | Byte-for-byte copies made before a migration, before a restore and by `state.py backup`. The newest 10 per file are kept (`backupsKeep`). |
| `state/.journal.json` | Exists only while a multi-file commit is in flight (see Durability). |
| `state/.state.lock/` | Directory lock held from read to write by every mutating command. |
| `state/.log/hooks.log` | Diagnostics from hooks, lock breaking, journal recovery, restores. |
| `exercises/<topic>/<name>/` | A coding task: README, starter, tests, `check.sh`, `.reference/` (never shown), `.attempts/` (every checked file). |

Paths for notes, diagrams, reviews, exercises and state come from `learn.config.json`.
`LEARN_NOW=<iso datetime>` overrides the clock (tests); days follow `timezone`.

## Node evidence

A node carries three independent fields (the v1 `status` is kept as a derived mirror: done / shaky / pending).

| Field | Values | Meaning |
|---|---|---|
| `coverage` | `pending`, `covered` | Whether the explanation or activity has happened. |
| `readiness` | `unknown`, `needs_repair`, `provisional`, `ready` | Whether current evidence supports building on the node. |
| `retention` | `unassessed`, `demonstrated`, `needs_review` | Evidence from a later review attempt (kind `review`). |
| `required` | true/false | Part of the agreed scope. `scope ID --optional --reason` records a reduction. |

`record` derives readiness from the attempt:

- pass, no substantive help, short-answer/code or a non-load-bearing multiple choice → `ready`
- pass on a load-bearing node by multiple choice alone, or pass with help (`nudge`/`substep`/`worked`/`corrected`) → `provisional`
- partial, fail, or "I don't know" → `needs_repair`
- an explicit `"readiness": "provisional", "reason": "..."` overrides (deliberate continuation; `revisit` records the plan)

Legacy v1 nodes that were `done` become `covered` + `unknown` (evidence was not recorded then). `unknown` does not block dependants; `next-node` notes it so the teacher checks just in time. `needs_repair` blocks the nodes that depend on it and nothing else.

`next-node` selects the first plan node whose prerequisites are all covered and none `needs_repair`. `finish` requires every required node covered with readiness `ready` or `provisional`, every exit criterion passed independently, and no open pending interaction. `stop` ends without recording completion.

## Attempts and the pending interaction

`ask` writes `topic.pending`:

```
id, type (short|mcq|code), topic, node, check, variant, rubric_version, kind
(initial|practice|review|repair|exit), exit (criterion id), params.order (mcq option
order, stable across restarts), stage (awaiting|recorded|completed), assistance
[...], asked_at, response, last_attempt, exercise, question_head
```

Question text and keys are resolved from the prep files (or the inline `--adhoc` JSON stored in the pending record), never from memory. `pending` shows the key only once an answer is recorded or with `--keys`.

`record` appends a compact attempt: `id, ts, node, check, variant, rubric_version, kind, response (≤400 chars), result (pass|partial|fail|unknown), required_met, required_missed, assistance, independent, misconception, quality, card, op`.

## Grade semantics (one mapping everywhere)

| q | Meaning |
|---|---|
| 5 | complete and precise |
| 4 | correct; small gap or hesitation |
| 3 | every required point met; a minor point missing or laboured |
| 2 | wrong, or a required point missing, or needed substantive help (`nudge` or more) |
| 1 | wrong |
| 0 | blank / "I don't know" |

`q >= 3` always means: all required points met and assistance none or a wording clarification. `record` and `srs.py grade --assisted / --missing-required` clamp anything higher to 2 and note `capped`. Rubric feedback (what was missing) is separate from scheduling quality.

## Scheduling rules (SM-2 kept; the evidence fed to it fixed)

- Attempt kinds: `initial` (the node's check), `practice`/`repair` (a reattempt right after an explanation), `review` (scheduled retrieval), `exit`.
- Success (q ≥ 3) on `practice`/`repair`: history only. Success on a day the card already advanced: history only. `review` before the due date: history only, marked `early`. Otherwise SM-2 advances (reps, interval, ease) and `last_graduated` is set.
- Any failure (q < 3): lapse, interval 1, due tomorrow, ease down, `lapses`+1. Same-day failure counts.
- `--op ID` (or `"op"` in `record`) makes replays no-ops (the id is stored in `applied_ops` of both files).
- Ease changes only when the schedule changes, so repetition cannot inflate it.
- Days are computed in the configured timezone.

## Cards

Cards are promoted from prepared checks marked `review: true` (durable concepts, recurring misconceptions, transferable procedures), not from every check. A card keeps all variants of its check; `due` picks the variant asked least recently and prints ready-to-paste text. `kind` is concept / misconception / procedure / task.

Key corrections:

- `amend-key` (clarify or extend): rubric version +1, old key kept in `key_history`, attempts stay valid.
- `invalidate-key` (the key was wrong or ambiguous): old key kept, attempts under it marked `valid: false` and excluded, schedule recomputed from the valid history only (fresh if none), `needs_replacement_check` set so the next `due` asks it as a new check. Unrelated cards are untouched.

Review sessions: `due` fills `reviewMinutes` (default 10; per-type cost `reviewCostMinutes`) oldest-due first; the rest are listed as deferred with their due dates unchanged. Code cards go last and are offered if time allows.

## Durability

- Every mutating command: lock → load both files → migrate in memory → mutate → validate schemas → check the on-disk `rev` still matches what was loaded (a hand edit in between is a `ConflictError`, nothing written) → write a journal holding the full content of every file → write each file atomically → delete the journal → release the lock.
- Any later load finds a leftover journal and re-applies it (idempotent), logging the recovery. Interruption between the two writes therefore cannot leave attempt, node and card state inconsistent.
- The lock is a directory; a lock older than `lockStaleSeconds` (60) is broken and logged. A command that cannot get it within 5 s reports and writes nothing.
- A missing file initialises to an empty default. A file that exists but does not parse blocks every mutating command with an actionable message, is never overwritten, and hooks degrade to a read-only notice.
- Migration is versioned (state 1→2, deck 1→2), idempotent, and preceded by byte-for-byte backups. v1 `done` → covered/unknown, `shaky` → covered/needs_repair; deck `points` prose → `explanation`; `|`-joined key points split; history entries dated on the creation day become `initial`, later ones `review`; nothing else is invented.

Restore: `python3 scripts/state.py restore --list`, then `restore state/backups/<file>.bak`. The replaced file is backed up first and the restore is logged.

## Commands

`state.py`: `show [--full]`, `topics`, `validate`, `migrate`, `backup`, `restore`, `history`, `start`, `goal`, `edge`, `pause`, `resume`, `stop`, `finish`, `log-target`, `plan-set`, `plan-show`, `plan-approve`, `node-add`, `node-edit`, `next-node`, `node-done`, `node-shaky`, `readiness`, `scope`, `next`, `checkpoint`, `correction`, `prep-topic`, `prep-node`, `prep-show`, `prep-status`, `source-add`, `source-digest`, `source-show`, `ask`, `pending`, `answer`, `hint`, `record`.

`srs.py`: `add`, `promote`, `due`, `grade`, `stats`, `list`, `show`, `history`, `forecast`, `suspend`, `unsuspend`, `amend-key`, `invalidate-key`.

`exercise.py`: `env`, `new`, `check [--file]`, `validate`, `list`.

### `record` input

```json
{"op": "optional-id", "result": "pass|partial|fail|unknown",
 "required_met": ["..."], "required_missed": ["..."],
 "assistance": "none|clarify|nudge|substep|worked|corrected",
 "misconception": "m1 or text", "quality": 4, "note": "...",
 "readiness": "provisional", "reason": "...", "revisit": "...",
 "promote": true, "covered": true, "next": "...", "summary": "..."}
```

Only `result` is required. Omitted `required_*` are inferred from the result; omitted `assistance` comes from the hints given; omitted `quality` is derived (pass 4, partial 2, fail 1, unknown 0) and clamped by the rules above.

### Prep file shapes

Topic (`prep-topic`): `capability`, `environment`, `chunks [{id,label,nodes}]`, `exit_criteria [{id,text,nodes,checks}]`, `sources [{id,url,title,section,verified}]`. Documents registered with `source-add` are entries `{id, kind: "document", path, role: primary|supplementary, title, pages, page_count, sha256, bytes, added, digested, digest_sha256}`; a later `prep-topic` keeps them even if its `sources` omits them.

Node (`prep-node`): `objective`, `why_needed`, `prerequisites`, `motivation`, `outline []`, `claims [{id,kind,text,scope,boundary,sources}]`, `misconceptions [{id,text,repair}]`, `checks [{id,type,role,load_bearing,review,kind,variants [{id,question,code,options,answer,required,accepted,disqualifying,rubric_version}],hints [3],exercise}]`, `code_exercise`, `review_suitability`, `status draft|ready`, `verified`, optional `source_refs [{source,pages,note}]`. A claim's `sources` may carry a locator: `"notes:p14"`.

Digest (`source-digest ID`, written by the `document-reader` subagent): `summary` (required), `scope_role`, `objectives []`, `sections [{id,title,pages,depth,concepts,notation,exercises,nodes}]`, `prerequisites_outside []`, `node_map [{node,label,pages,focus,depth}]` (a node not in the plan is a proposal), `conflicts [{claim,pages,issue,nodes,resolution}]`. Pages are physical PDF pages. The digest stores the file hash; `prep-status`, `validate` and `source-show` report a document that is missing, not digested, or changed since its digest.

## Tests

`bash scripts/selftest.sh` runs a smoke test in a temp copy with its own config (every writable directory under the temp root) and then the regression suite `python3 -m unittest discover -s scripts/tests`. The suite covers migration idempotence, corrupt-file protection, plan validation, prerequisite gating, completion rules, pending-interaction recovery, replay safety, scheduling rules, key invalidation, journal recovery, lock conflicts, retry files, C exercise validation and smoke-test isolation. It never touches the configured vault or the live state.
