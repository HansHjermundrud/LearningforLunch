---
name: review
description: Run a spaced-repetition review session on the cards that are due (short-answer, multiple-choice and coding cards from finished lessons). Use when the learner says /review, asks what is due, or wants to practise or refresh earlier topics.
argument-hint: [topic-slug] [--limit N]
---

# Review session

Reviews are separate from lessons. They do not teach new material; they test recall of cards the lessons created, grade honestly, and reschedule with SM-2. Keep it brisk.

## Start

1. Get the due cards: `python3 scripts/srs.py due --json` (add `--topic <slug>` or `--limit N` if the learner asked for it). If nothing is due, say so, show `python3 scripts/srs.py forecast --days 7`, and offer to review ahead of schedule or stop.
2. Turn on mirroring to a dated review note:
   `python3 scripts/state.py log-target "<reviewsDir>/<today> review.md"` where reviewsDir comes from `learn.config.json` (default `notes/reviews`) and today is the injected date.
3. Tell the learner how many cards are due and which topics.

## For each card, one at a time

- **short**: ask the question in plain chat, end the turn, wait. Grade the reply 0-5 against the stored answer and key points (5 complete and precise, 4 small gap, 3 core present but a key point missing, 2 wrong but recognised, 1 wrong, 0 blank or "I don't know"). Give the model answer and what was missing. Then `python3 scripts/srs.py grade <id> <q>`.
- **mcq**: ask with `AskUserQuestion` using the stored options in a shuffled order plus "I don't know" last. Grade: 5 if right, 2 if wrong, 0 for "I don't know". Explain briefly. Then grade the card. **If the card contains code**, skip `AskUserQuestion` (it renders code on one line): show the code as a fenced ```` ```c ```` block in plain chat, reformatted to one statement per line with pragmas on their own lines, list the options as A), B), C) ... with "I don't know" last, and end the turn.
- For any card type, code in the question is always shown as a fenced, properly line-broken block, never inline.
- **code**: show the task summary and the exercise folder from the card. Ask the learner to solve it again in a fresh file inside that folder (for example `retry-<today>.py`) or to describe the approach if time is short. When they say done, run `bash <folder>/check.sh` adapted to the retry file, or review the description. Grade 0-5 and record it.

Never reveal the answer before the learner has answered or explicitly given up. If a wrong answer exposes a misconception, note it in one sentence and append a dated line to `LEARNER.md` under "Standing notes" if it is likely to recur.

## Finish

1. Summarise: cards reviewed, grades, what to revisit. Suggest a re-teach only when a card scored 0-2 twice in a row (check `python3 scripts/srs.py show <id>`).
2. `python3 scripts/srs.py stats` and tell the learner when the next batch is due.
3. Turn mirroring off: `python3 scripts/state.py log-target --clear` (unless a lesson topic is active, in which case restore it with `python3 scripts/state.py resume <slug>`).
