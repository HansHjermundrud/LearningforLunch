# Teacher presentation notes

## Opening

“Learning for Lunch turns Claude Code into a persistent tutor. Claude handles teaching and assessment. Python keeps track of the evidence, controls what can come next, and schedules review. The conversation can disappear without losing the lesson.”

Show **How it works**. Point to the three columns: teaching behavior, executable rules, and durable memory. Then return to **Live classroom**.

## State what the demonstration is

“The lesson and responses here are prepared examples. The Python engine and saved state are real. We use an isolated copy so that a demonstration does not change my personal learning records. The page does not call a model or pretend to perform AI grading.”

## The clearest moments to show

### Save first, then wait — steps 1–3

The pending question is saved before an answer arrives. Step 2 saves the answer without grading it. Step 3 supplies an explicit assessment and lets the engine record the consequences.

**Point to:** the right-hand question panel; the three evidence counters; Engine trace → Input payload versus Output.

**Say:** “The engine receives an assessment. It does not independently read an answer and decide that it is correct.”

### A misconception changes the path — steps 4–6

Equivalent fractions receives a failing assessment. Addition becomes blocked, while the number-line branch is still eligible and can proceed.

**Point to:** the red concept, blocked edge, and still-open branch.

**Say:** “Coverage means we encountered it. Readiness means there is evidence we can build on it. Those are not the same.”

### Help changes what the answer proves — steps 7–9

A repair question receives a recorded hint. The actual recovery hook reconstructs the same pending interaction. The assisted pass becomes provisional and scheduling quality is capped at 2, even though the sample assessor requested 4.

**Point to:** the recorded assistance; Engine trace after step 8; the quality cap after step 9.

**Say:** “A supported success matters, but the system should not confuse it with independent recall.”

### Finish is not “remembered forever” — steps 10–14

A transfer check satisfies the exit criterion. The demo clock then moves forward. The actual scheduler changes one card's interval from 1 to 6 to 15 days. A later failure updates another concept's retention without deleting coverage or downstream learning.

**Point to:** Review lab, then Evidence ledger.

**Say:** “What I have been taught, what I can currently build on, and what I remember later are three separate judgments.”

## Questions a teacher may ask

**Does this replace a teacher?**

It provides a particular tutoring workflow. The model still makes pedagogical and grading judgments, and those judgments can be wrong. The value here is that preparation, evidence and consequences are inspectable instead of disappearing in an unstructured chat.

**Is the AI training itself on my answers?**

There is no model-weight training loop in this project. It adapts through saved learner evidence, profile observations, revised preparation and scheduled review.

**Is every design rule guaranteed by Python?**

No. Some are teaching instructions for Claude; others are enforced by the scripts. The uploaded code, for example, can mark an unassisted repair pass ready despite the more conservative wording in the teaching policy. The dashboard exposes the implementation rather than replacing it with an idealized version.

**Why not mark every correct answer as mastered?**

Help, answer type, missing required points and timing affect what the answer demonstrates. The system keeps those distinctions. Review evidence is separate from immediate readiness.

**Can I see a real lesson in this page?**

Yes: connect the dashboard to the same checkout where Claude Code is teaching and switch to Live project. It observes saved state. It does not stream unsaved teaching, subagent activity or hidden reasoning. Live controls require an explicit launch flag.

## Closing

“The contribution is not just asking a chatbot to teach. It is making the teaching loop persistent and evidence-driven: prepare, ask, assess, record, repair when necessary, and revisit later.”
