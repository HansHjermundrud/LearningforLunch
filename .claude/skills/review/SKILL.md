---
name: review
description: Run a spaced-repetition review session on the cards that are due (short-answer, multiple-choice and coding cards from lessons). Use when the learner says /review, asks what is due, or wants to practise or refresh earlier topics.
argument-hint: [topic-slug] [--limit N] [--budget MIN]
---

# Review session

Reviews test recall of prepared cards, grade honestly against the committed key, and reschedule. They do not teach new material. Keep it brisk and conversational.

## Start

1. `python3 scripts/srs.py due --json` (add `--topic <slug>`, `--limit N` or `--budget MIN` if asked). The default selection fits the configured time budget (`reviewMinutes`, 10 by default), oldest due first; deferred cards keep their due dates and are listed. Do not ask the learner for a budget. Long coding cards are placed last: offer them if time allows.
2. If nothing is due: say so, show `python3 scripts/srs.py forecast --days 7`, offer to review ahead of schedule (an early success does not accelerate the schedule) or stop.
3. Mirror to a dated review note: `python3 scripts/state.py log-target "<reviewsDir>/<today> review.md"` (reviewsDir from `learn.config.json`).
4. Say how many cards, which topics, roughly how long.

## For each card, one at a time

Use the `ask_text` the `due --json` output gives you: it already picks the variant asked least recently, puts code in a fenced block and letters the options with "I don't know" last. Paste it, end the turn, wait.

- **short**: grade against the stored answer and required points. Quality: 5 complete and precise, 4 correct with a small gap or hesitation, 3 core present and every required point met but a minor point missing, 2 wrong or missing a required point, 1 wrong, 0 blank or "I don't know". Give the model answer and what was missing.
- **mcq**: 5 if right, 2 if wrong, 0 for "I don't know". Explain in one or two sentences.
- **code**: show the task summary and folder. Ask for a fresh file inside that folder (`retry-<today>.c`) or, if time is short, an explanation of the approach (that is different evidence; grade it as an explanation, at most 4). When they say done: `python3 scripts/exercise.py check <folder> --file retry-<today>.c`. Passing runs do not prove race-freedom: ask what synchronizes what.

Then one command: `python3 scripts/srs.py grade <id> <q> --kind review --variant <variant> [--assisted] [--missing-required] [--note "..."]`. `--assisted` when you had to hint; `--missing-required` when a required point was missing; either caps the quality at 2, which is the documented meaning of 3+. A card whose key was corrected (`needs a fresh check` in `due`) is asked normally; its old attempts no longer count.

Never reveal the answer before the learner answers or gives up. If a wrong answer exposes a misconception likely to recur, append one dated line to `LEARNER.md` under "Standing notes". Do not announce grades' internals, card ids or scheduling.

## Finish

1. Summarise: cards reviewed, what to revisit. Suggest a re-teach only when a card scored 0-2 twice in a row (`python3 scripts/srs.py history <id>`).
2. `python3 scripts/srs.py stats`: when the next batch is due.
3. `python3 scripts/state.py log-target --clear`, or `python3 scripts/state.py resume <slug>` if a lesson topic is active.
