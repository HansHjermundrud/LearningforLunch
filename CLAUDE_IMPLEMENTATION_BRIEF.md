# Improve Learning for Lunch: reliable preparation, lightweight teaching

Repository: https://github.com/HansHjermundrud/Learning

Prepared: 2026-09-25

## Your task

Implement the improvements in this brief in the existing repository. This is an implementation request, not a request for another general review. Inspect the current branch first: the findings below describe the version reviewed on 2026-09-25 and may already have changed.

The owner's most important constraint is:

**Actual teaching must stay conversational and have low overhead. More work is acceptable when preparing the nodes, assessments, and lesson plan.**

Preserve the useful core: Claude as tutor, persistent lesson state, motivated explanations, honest assessment, programming exercises, and spaced review. Move research, answer validation, assessment design, and dependency checking into preparation. Make the normal teaching turn a small read/teach/check/save loop.

The owner is using this inside Claude and accepts the existing chat/LaTeX presentation. Do not redesign the Obsidian interaction, build a UI, replace the rendering stack, or migrate the whole project to another platform. Preserve existing notes and user paths.

## 1. Non-negotiable design constraints

1. Do not introduce a research call, secondary grader, diagram generation, full-plan inspection, or multi-agent discussion for every teaching turn.
2. Prepare reusable lesson material once and reuse it. Revalidate when a relevant assumption, source version, goal, or claim changes.
3. Keep state bookkeeping out of the learner-facing response. Avoid announcing routine saves, card IDs, grading internals, and dependency checks.
4. Ask one substantive question at a time. Do not require the learner to complete forms, choose modes repeatedly, approve every node, or self-rate every answer.
5. A node needs enough evidence to continue safely; it does not need delayed mastery before the lesson may proceed. Retention checks happen later.
6. Do not mistake an immediate corrected answer, a hinted solution, or a lucky multiple-choice selection for independent understanding.
7. Do not remove necessary mathematical or technical conditions just to make a statement sound foundational.
8. Keep the standard-library Python architecture unless a demonstrated requirement makes a dependency necessary. Do not add a web server, background job system, vector database, or general orchestration framework.
9. Preserve existing learner history. Migrate conservatively; never invent past answers, hint counts, elapsed times, or delayed successes.
10. Verify uncertain new claims when they arise. Low overhead is not permission to confidently improvise an answer key.

### Operational targets

Treat these as design targets, not reasons to suppress necessary work:

| Stage | Expected work |
|---|---|
| Initial planning | Batched research, goal alignment, dependency checks, validated questions and rubrics, practical exercise preparation. |
| Ordinary explanation of a prepared node | No web research, no new subagent, no mandatory diagram render. |
| Ordinary answer/feedback turn | One local command can record the attempt, update relevant state, and prepare the next interaction. Avoid separate commands for each field. |
| Context recovery | One compact snapshot plus the current node and pending question. Do not load the full transcript or every card. |
| User follow-up outside prepared material | Answer from established knowledge when justified; verify a genuinely uncertain claim narrowly, then cache the result. |

Do not attempt to guarantee model latency in milliseconds. Demonstrate reduced tool calls and smaller routine context with representative transcripts.

## 2. Inspect and protect the existing project

Read `CLAUDE.md`, `LEARNER.md`, `learn.config.json`, relevant `.claude/skills/*/SKILL.md` files, `.claude/agents/researcher.md`, and the scripts you will change. Inspect current state and deck schemas and the existing smoke test.

Follow applicable repository instructions. Preserve unrelated user changes. Work on an appropriate local branch if useful; do not push or merge remotely unless separately authorized.

Before migrations, make recoverable backups of the existing state and deck. Backups must preserve the original bytes. Migration must be versioned and idempotent. Use isolated fixtures for all destructive/corruption tests.

The existing `selftest.sh` copies the configuration unchanged into its temporary directory. With absolute note paths, that can still write into the real notes directory. Fix this before relying on the test: explicitly replace every writable configured directory with a path inside its temporary root.

## 3. Fix the teaching philosophy without losing motivated explanations

Update the teaching instructions and researcher brief. Keep explanations that connect new ideas to what the learner already understands. Remove the demand that foundations must always be unconditional, caveat-free truths.

Distinguish:

- **Definition or convention:** what a term means or what an API deliberately specifies.
- **Assumption:** something adopted for this example or model.
- **Guarantee:** what follows under stated conditions.
- **Simplification:** a useful approximation with a known boundary.

A simple explanation can be accurate and conditional. Do not pretend arbitrary syntax, API choices, or historical conventions are logically inevitable. Motivate their purpose without inventing a derivation.

Remove unsupported assertions such as “understood facts don't rot” and claims that the brain instantly commits to unconditional truths. They should not govern the tutor's behavior.

For each load-bearing claim during preparation, record its scope, relevant assumptions, and a counterexample or boundary where useful. These are preparation notes; do not recite the complete list during teaching. Surface a condition when it matters for the explanation or assessment.

### Audit these existing OpenMP examples

Recheck them against authoritative sources and the configured language/compiler target:

1. `correct = race-free`: race freedom alone does not establish functional correctness or freedom from deadlock.
2. `parallelizable iff iterations are independent`: distinguish a straightforward unsynchronized work-sharing loop from parallelization using reductions, explicit ordering, or algorithm changes.
3. `every other construct only divides work`: this overstates the role of constructs such as barriers and synchronization directives.
4. Stack location versus OpenMP data-sharing semantics: do not substitute an implementation picture for the specification's rules.
5. “Only associative operations” for reductions: distinguish mathematical requirements for order-independent results from operations actually supported by OpenMP and the numerical behavior of floating-point reductions.

The existing card `cu1dsb` says all threads print zero after a shared pointer is set to thread 0's local `mine`. This is not a portable output guarantee under OpenMP 5.2: `mine` has a private data-sharing attribute, and the memory-model section restricts access by another task to private variables outside its stated exceptions. Audit the question, answer, explanation, and related nodes before reusing them.

Primary references to verify:

- OpenMP 5.2 §5.1.1, Variables Referenced in a Construct: https://www.openmp.org/spec-html/5.2/openmpsu33.html
- OpenMP 5.2 §1.4.1, Structure of the OpenMP Memory Model: https://www.openmp.org/spec-html/5.2/openmpsu9.html
- OpenMP 5.2 §5.5.2, OpenMP Reduction Expressions: https://www.openmp.org/spec-html/5.2/openmpsu46.html

Be precise about the specification's wording, including “unspecified” versus “undefined,” and any separate base-language rules. A successful compiler run does not prove that behavior is guaranteed.

If an answer key is wrong or ambiguous, preserve the original version and attempt history, record the correction, exclude invalid assessment evidence from future readiness decisions, and arrange a replacement check. Do not silently relabel the learner's old answer as a failure. Do not reschedule unrelated cards.

## 4. Prepare a compact lesson package before teaching

Extend the planning workflow so it produces verified material that the teacher can use without researching or designing a new assessment on every turn.

Keep files and schemas simple. A versioned JSON plan with Markdown node material, or another small extension of the existing structure, is sufficient. The data layout below is a requirement for information, not a mandate for one file per field or a large abstraction layer.

### Topic-level preparation

Record:

- Concrete target capability: what the learner should be able to explain, decide, derive, or build.
- Relevant environment and assumptions, such as C, compiler version, and supported OpenMP features.
- Required versus optional nodes and their genuine prerequisites.
- A small sequence of session-sized chunks; avoid one sprawling map.
- Exit-assessment criteria aligned to the goal.
- A small source registry with stable IDs, URLs, relevant sections, and verification dates/versions where useful.

If the current environment is already known, reuse it. Ask only for missing information that changes what should be taught.

### Node-level preparation

Prepare the following for each node needed in the upcoming session:

1. Stable ID, short label, and observable learning objective.
2. Prerequisites and why the node is needed for the goal.
3. A brief motivating example or problem.
4. A concise explanation outline, including any derivation that actually helps.
5. Important claims, assumptions, boundaries, and references to source IDs.
6. Likely misconceptions and brief repair explanations.
7. One normal check and, where useful, one fresh alternative for an ambiguous result or later transfer check.
8. A committed answer key, required points, accepted alternative reasoning, and genuinely disqualifying misconceptions.
9. A small hint ladder for substantive problems: prompt attention, suggest a substep, then show a partial worked step.
10. A code exercise specification where code best demonstrates the objective.
11. Review suitability: whether this is a durable concept worth scheduling, not simply whether a question exists.

Prepare a full outline for a large topic, but fully develop only the upcoming session's nodes and exit criteria. Extend the prepared material at session boundaries or when scope changes. Avoid generating a textbook and dozens of unused questions before the first lesson.

### Preparation checks

Before marking material ready:

- Validate the dependency graph: unique IDs, existing references, no cycles or self-dependencies.
- Check that questions are self-contained and that their keys follow from their explicit assumptions.
- Check that multiple-choice distractors are genuinely wrong under those assumptions and do not reveal the answer through wording.
- Check that required points test the objective rather than demand the model answer's exact phrasing.
- Verify important technical claims and assessment keys against primary documentation or another appropriate authoritative source.
- Compile/run code examples when useful, while distinguishing observed execution from specification guarantees.
- Link each core goal to assessment evidence; avoid nodes that exist only to make the map look complete.

Use the existing researcher during preparation in topic-sized batches if appropriate. Its result must be persisted in the prepared material, not stranded in a disposable conversation.

Recheck only affected material when something changes. Do not refetch every source at every session start.

## 5. Keep live teaching simple and adaptive

### Two natural entry paths

- A specific question or request for a quick explanation should get a direct answer. Do not force probing, a plan, card creation, or a full lesson lifecycle.
- `/teach <topic>` or an explicit structured-learning request uses the prepared lesson workflow.

Infer the path from the request. Do not show a mode-selection form each time.

### Start a structured lesson

Reuse the learner profile and existing evidence. Limit the initial diagnostic to a few informative questions, aiming for roughly 3–5 minutes unless the learner wants a deeper assessment. Do not require finding a failure ceiling along every strand before useful teaching can begin. Test uncertain prerequisites when they become relevant.

Clarify the goal only if needed. Present a short plan and obtain agreement once for a new substantial scope. Resume an approved plan without asking for approval again. Small adjustments do not need repeated confirmation unless they meaningfully change the goal or workload.

### Normal node loop

1. Briefly motivate the idea.
2. Explain or guide a derivation at a depth appropriate to the learner.
3. Make the important connection to prior material.
4. Ask one check when evidence is needed, then wait.
5. Give concise, honest feedback and continue, or repair the specific gap.

These are teaching intentions, not mandatory visible headings or five separate tool calls. Do not repeat a mini-lecture after every correct answer. Do not print a local dependency map before every node. Show a map at planning, meaningful transitions, or on request.

Use Socratic questioning when the next step is reasonably discoverable. After one or two unproductive attempts, give an example or a small hint rather than prolonging a guessing game. Record assistance automatically.

Use one check by default, adding another only to resolve a concrete uncertainty. Use the prepared fresh variant when a correct answer may merely repeat the explanation. Do not impose an extra exam at every node.

## 6. Separate lesson progress from evidence of learning

Do not use a single `done` flag to mean both “we covered this” and “the learner retains it.” Use a small explicit distinction, for example:

| Field | Suggested values | Meaning |
|---|---|---|
| Coverage | `pending`, `covered` | Whether the explanation/activity has occurred. |
| Readiness | `unknown`, `needs_repair`, `provisional`, `ready` | Whether current evidence supports building on this node. |
| Retention | `unassessed`, `demonstrated`, `needs_review` | Evidence from a later eligible retrieval attempt. |

Equivalent naming is fine if semantics are documented and used consistently.

For a load-bearing node, `ready` normally requires an independent response meeting its prewritten minimum criteria. An assisted response can support `provisional`; a known unresolved prerequisite misconception remains `needs_repair`.

A delayed retention check is not a prerequisite for continuing the lesson. Allow deliberate continuation from provisional knowledge when pedagogically sensible, with a short recorded reason and a planned revisit. Do not make this a learner-facing approval ritual.

Multiple-choice success alone should not establish independent mastery of a derivation or coding objective. Conversely, do not demand a derivation when the objective is simply recognizing an API feature.

For new attempts, retain compact evidence: question/version ID, response, correctness against required points, assistance, essential misconception if any, timestamp, and whether this was practice, an initial check, or delayed review. Reuse an existing durable answer record when possible rather than duplicating full transcripts.

For old `done` nodes, retain their status as legacy coverage and their original summaries. Mark missing evidence as unknown. Do not automatically force the learner to repeat the entire course after migration; check uncertain foundations just in time.

Topic completion must require the agreed required coverage/readiness and goal-aligned exit evidence. Unfinished optional material may remain optional. A learner can pause, stop, or explicitly reduce scope without falsely recording mastery.

## 7. Make continuation and state updates reliable without extra ceremony

Free-text `NEXT` is useful for humans but insufficient as the only recovery mechanism. Persist a structured pending interaction before asking a question or handing over a code task.

Store at least:

- Interaction ID and type.
- Topic and node IDs.
- Question/task ID and rubric version.
- The actual selected variant, including concrete parameters if parameterized.
- Stage: awaiting response, response recorded, or completed.
- Assistance already given and the latest relevant attempt ID.

Resolve question text and the answer key from durable prepared material. Never depend on reconstructing them from the model's memory. Do not reveal the answer to the learner before they respond or explicitly give up.

After compaction or restart, recover the pending interaction first. If an answer was recorded but not graded, resume grading it; if it is still waiting, preserve that state. Do not accidentally generate a different question or grade the same answer twice.

Provide one convenience command or extend an existing command to apply a validated batch of related updates. A normal answer turn should be able to record the attempt, update readiness, apply any eligible review result, set the next interaction, and return the minimal next-node context in one local call.

Exact command names are your choice. Keep existing commands compatible where practical. Prefer structured JSON input for multi-field updates rather than fragile shell escaping.

State and deck updates must be recoverable and idempotent when an operation spans files. Choose a small documented approach, such as a recoverable pending-operation record plus operation IDs; do not claim two independent atomic file replacements constitute an atomic transaction. Test interruption between writes.

Hook output should contain a compact summary, pending interaction, and the next useful action. Keep detailed history available on demand. Hook failure should leave the chat usable while logging diagnostics; it must not claim a save succeeded when it did not.

## 8. Improve review selection and grading before changing algorithms

Keep SM-2 initially. The main problems are the evidence being fed into it and what becomes a card. A new scheduler is not the first priority.

### Card selection

- Log checks as attempts; do not automatically make every check, repair, and follow-up a permanent card.
- Promote selected durable concepts, recurring misconceptions, and transferable procedures.
- Start with approximately 1–2 useful review prompts per core concept when appropriate, not a hard quota.
- Deduplicate or group prompts targeting the same skill. Avoid consecutive near-identical questions that cue each other's answers.
- Make prompts self-contained. Replace references like “the n1 snippet” with the necessary code and assumptions.
- Use a small bank of prepared, validated variants. Record which was asked. Do not generate and research a new question on every review turn.
- Distinguish explaining a coding approach from implementing and validating it. Both are useful, but they are different evidence.

### Grade semantics

Separate rubric feedback from scheduling quality. A missing required point, unresolved core misconception, or answer requiring substantive help should not count as successful independent recall merely because the teacher assigns “3/5.”

Use a documented mapping consistent across teaching, review, code tasks, and `srs.py`. If retaining SM-2 qualities, `q >= 3` must mean the minimum independent-recall criteria were met. Difficulty or hesitation can lower quality within the passing range; a missing essential condition cannot be treated as only hesitation.

Do not add mandatory confidence questions or extra rating steps. Infer assistance from the interaction and use the committed rubric.

### Scheduling correctness

Distinguish initial learning, immediate reattempts, and later reviews. An explanation followed by another attempt must not masquerade as a second spaced retrieval.

At minimum:

- Replaying the same operation/attempt ID has no additional effect.
- A same-local-day success must not graduate the interval a second time. Same-day failure may trigger repair/relearning; do not ignore it.
- Initial assessment establishes the first review date; immediate practice does not skip it.
- Reviews ahead of schedule do not silently accelerate the schedule as if the interval had elapsed.
- Use the configured timezone for day boundaries and an injectable clock for tests.
- Invalidated answer keys never count as evidence of poor learner performance.

Make default review workload bounded, for example a configurable 10-minute target with a sensible card-count fallback. Do not ask for the budget every session. Long coding tasks should be explicitly offered within available time. If a backlog exists, prioritize transparently and preserve remaining due dates; do not silently forgive overdue work or stop all new learning.

## 9. Strengthen the existing scripts

### Dependency and completion rules

Fix `state.py` so next-node selection checks prerequisites instead of selecting the first pending node. Reproduce this case: `n1` is shaky, `n2` is independent, and `n3` depends on `n1`; completing `n2` must not automatically schedule `n3`.

When no ordinary node is eligible, report the specific repair or missing preparation needed. A later review failure can flag affected prerequisites without erasing downstream work wholesale.

Reject malformed plans, missing dependency IDs, duplicate IDs, cycles, and invalid status values before writing. Do not report “all nodes done” when shaky or required pending nodes remain. `finish` must validate the agreed completion criteria rather than unconditionally setting a flag.

### Persistence and schema safety

The current `read_json` fallback conflates missing files and unreadable/corrupt files. Missing new state may initialize safely; existing invalid state must block mutations, preserve the original, and produce an actionable diagnostic. Hooks can still return successfully without permitting destructive writes.

Use schema checks for plans, cards, attempts, and pending interactions. Normalize existing irregularities deliberately, such as legacy `points` versus `key_points`, without inventing missing evidence.

Keep atomic writes. Add a lightweight lock or conflict check around read-modify-write so a hook and command cannot silently overwrite each other's changes. Handle stale locks and failures clearly. Do not silently choose an old backup as current state without recording recovery.

Backups and migration should be bounded and understandable. The project does not need an enterprise backup system.

## 10. Make practical programming work match the current goal

Add a real C/OpenMP exercise template alongside Python and JavaScript. Detect or configure the compiler, use appropriate warnings and `-fopenmp`, and give a clear diagnostic when support is unavailable.

For appropriate exercises, prepare:

- A clear task, inputs/outputs, constraints, and small examples.
- A starter that does not contain the learner's solution.
- A serial reference or other independent oracle.
- Checks over several input sizes and thread counts.
- Numeric tolerances when floating-point results require them.
- A timeout and useful failure output.
- An optional performance experiment separate from correctness grading.

Do not use “the race did not happen in these runs” as a proof of correctness. Require relevant reasoning about synchronization/data ownership. Likewise, noisy timing results should not automatically fail an otherwise correct solution.

Validate exercise tests against a correct reference and at least one plausible incorrect implementation during preparation. Keep reference solutions out of the learner-facing starter and normal teaching context.

Support a retry file/path explicitly so a review runs the new attempt rather than accidentally testing the original solution. Preserve previous attempts. Never overwrite the learner's solution to make tests pass.

Introduce small predict/run/explain/modify activities before the end of a long programming topic. Do not impose a 25-minute exercise after every node; use short activities and a few substantial tasks aligned to the goal.

## 11. Acceptance tests and verification

Extend the existing test approach with targeted regression tests. Tests must use temporary state, notes, exercises, and an injectable clock. Never write into the configured real vault or live learner state.

Cover these behaviors:

1. Legacy state/deck migrate twice without further changes or lost history.
2. A corrupt existing deck blocks writes and remains byte-for-byte preserved.
3. Unknown dependency, duplicate node, and cyclic plans are rejected without mutation.
4. A shaky prerequisite prevents automatic selection of its dependent node.
5. Independent eligible nodes can still proceed; the scheduler does not freeze the entire topic unnecessarily.
6. An incomplete required plan or missing exit evidence cannot be falsely finished.
7. A deliberately optional node does not prevent completion of the agreed required scope.
8. A pending question survives restart with the same variant and rubric version.
9. A recorded-but-ungraded response resumes without asking a different question.
10. Replaying an attempt or interrupted operation does not double-grade or double-schedule it.
11. Same-day successes do not advance a card from its first interval to six days merely through immediate repetition.
12. A later eligible successful review does advance the schedule; failure and timezone boundaries behave as documented.
13. A response missing an essential rubric point cannot count as successful independent recall.
14. Correcting an invalid key preserves history and does not penalize the learner for that key.
15. Recovery after an interrupted multi-file operation leaves attempt, node, and deck state consistent.
16. Concurrent state writes cannot silently drop an update.
17. A retry coding assessment executes the supplied retry file.
18. Correct and deliberately flawed exercise implementations produce the expected test results.
19. Smoke tests remain isolated even when the user's configuration contains absolute paths.

Also run a few short behavioral scenarios using prepared material:

- Quick question: direct useful answer with no forced onboarding.
- Correct response: concise feedback, one persistence operation, no research or map regeneration.
- Wrong response: targeted repair and a useful hint, not a new planning ceremony.
- Continuation: resumes the pending interaction without re-probing completed material.
- Follow-up outside scope: a bounded factual check when needed, then reuse of the verified result.

Record expected versus observed tool calls. If live Claude execution is unavailable, distinguish static/scenario checks from an actual live run. Do not claim conversational performance was measured when it was not.

## 12. Implementation sequence and deliverables

Work in this order, while keeping the existing workflow usable:

1. Isolate tests, protect state, add schema/migration safeguards, and fix confirmed dependency/completion failures.
2. Correct foundational instructions and audit affected existing OpenMP material and answer keys.
3. Add prepared node material and structured pending interactions, with a small batched state-update path.
4. Implement evidence/readiness distinctions, grading consistency, selective card promotion, and scheduling safeguards.
5. Add the C/OpenMP exercise path and remove unnecessary runtime ceremony from the skills and hooks.
6. Run the regression checks and representative teaching scenarios; update documentation.

Likely files include `CLAUDE.md`, the teach/review/code-task/checkpoint/status skills, the researcher instructions, `learnlib.py`, `state.py`, `srs.py`, `exercise.py`, session hooks, and `selftest.sh`. Change only what is needed; keep the visualization and note-export workflow compatible.

Document the new data semantics, commands, migration/restore procedure, and what runs during preparation versus actual teaching. Update instructions together with code so the teacher does not continue following an obsolete workflow.

At completion, provide:

- A concise account of implemented behavior and important tradeoffs.
- The tests actually run and any limitations.
- A list of corrected or flagged learning material, with source references.
- Confirmation of preserved history and the backup/restore location.
- One example prepared node and a short sample of an ordinary low-overhead teaching exchange.
- Any genuinely blocked work, with a concrete reason; do not present unimplemented items as finished.

The result should let the tutor arrive well prepared, teach naturally, assess honestly, and resume reliably. More preparation is acceptable; recurring ceremony during learning is not.
