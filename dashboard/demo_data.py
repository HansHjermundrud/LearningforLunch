"""Presentation material, not model-generated assessments or engine rules."""
TITLE = "Fractions: from parts to sums"
SLUG = "fractions-demo"
GOAL = "Explain and add fractions by reasoning about equal-sized parts."
PLAN = {"nodes": [
    {"id": "parts", "label": "Equal parts", "depends": [], "why": "Define what a denominator counts."},
    {"id": "equivalent", "label": "Equivalent fractions", "depends": ["parts"], "why": "Change the unit without changing the amount."},
    {"id": "add", "label": "Add unlike fractions", "depends": ["equivalent"], "why": "Combine quantities expressed in the same unit."},
    {"id": "numberline", "label": "Fractions on a line", "depends": ["parts"], "why": "An independent branch: locate quantities between zero and one."},
]}

def check(question, answer, required, second=None):
    variants = [{"id": "v1", "question": question, "answer": answer, "required": required}]
    if second:
        variants.append({"id": "v2", "question": second[0], "answer": second[1], "required": required})
    return {"id": "q1", "type": "short", "role": "normal", "load_bearing": True,
            "review": True, "kind": "concept", "variants": variants,
            "hints": ["What does the denominator tell you about the size of one part?",
                      "Imagine the same whole divided into equal-sized pieces.",
                      "Rename the amount in equal-sized pieces before comparing or combining it."]}

PREP = {
    "parts": {
        "objective": "Explain why the parts counted by a fraction must be equal-sized.",
        "why_needed": "Without a common-sized unit, counting pieces does not describe an amount.",
        "motivation": "Cut a pizza into four unequal pieces. Is every piece one quarter?",
        "outline": ["Choose one whole.", "Divide it into equal-sized parts.", "The denominator describes that partition; the numerator counts parts."],
        "misconceptions": [{"id": "unequal", "text": "Any one of four pieces is one quarter.", "repair": "Compare a tiny slice with a slice covering half the same pizza."}],
        "checks": [check("A cake is cut into four unequal pieces. Is each piece one quarter? Explain.",
                         "No. Quarters are four equal-sized parts of the same whole.",
                         ["parts must be equal-sized", "refer to the same whole"],
                         ("What must be true of eight pieces for each to be one eighth?", "They must be eight equal-sized parts of the same whole."))],
        "status": "ready"
    },
    "equivalent": {
        "objective": "Explain why one half and two quarters describe the same amount.",
        "why_needed": "A common denominator renames an amount; it does not make the amount larger.",
        "motivation": "Split each of two equal halves in half again. What changed?",
        "outline": ["Start with one of two equal parts.", "Split every part into two equal subparts.", "Twice as many selected pieces, each half as large, preserves the amount."],
        "misconceptions": [{"id": "bigger-numbers", "text": "Two quarters is larger because two is larger than one.", "repair": "Use one unchanged whole; show the selected area before and after splitting."}],
        "checks": [check("Why is 1/2 equal to 2/4, rather than smaller?",
                         "Each half is split into two quarters. Twice as many half-sized pieces preserve the amount of the same whole.",
                         ["pieces become half as large", "twice as many pieces preserve the same amount"],
                         ("Explain why 2/3 and 4/6 name the same amount.", "Each third is split into two sixths; twice as many half-sized pieces preserve the same amount."))],
        "status": "ready"
    },
    "add": {
        "objective": "Add one half and one quarter by expressing both in quarters.",
        "why_needed": "Counting unlike units together gives the wrong total.",
        "motivation": "You ate half of a cake and then another quarter of the same cake.",
        "outline": ["Rename one half as two quarters.", "Add two quarters and one quarter.", "The result is three quarters, not two sixths."],
        "misconceptions": [{"id": "add-denominators", "text": "Add the numerators and denominators separately.", "repair": "Ask what size of piece a sixth would be and why the original pieces did not become sixths."}],
        "checks": [check("What is 1/2 + 1/4? Explain why the denominator stays four.",
                         "1/2 is 2/4, so 2/4 + 1/4 is 3/4. We are counting quarter-sized pieces.",
                         ["rename one half as two quarters", "three quarter-sized pieces give three quarters"])],
        "status": "ready"
    },
    "numberline": {
        "objective": "Place three quarters between one half and one on a number line.",
        "why_needed": "Connect a part-whole representation with a numerical position.",
        "motivation": "Where would you stand after moving three of four equal steps from zero to one?",
        "outline": ["Divide the interval from zero to one into four equal steps.", "Move three steps from zero.", "The position is greater than one half but less than one."],
        "misconceptions": [{"id": "count-marks", "text": "Count drawn marks rather than equal intervals.", "repair": "Trace the spaces between zero and one."}],
        "checks": [check("Where is 3/4 relative to 1/2 and 1 on a number line?",
                         "It is greater than one half and less than one.",
                         ["greater than one half", "less than one"])],
        "status": "ready"
    }
}
EXIT = {"id": "transfer", "text": "Use a common unit to explain a new fraction sum.", "nodes": ["add"],
        "checks": [{"id": "exit-sum", "type": "short", "role": "exit", "review": False,
                    "variants": [{"id": "v1", "question": "A friend says 1/3 + 1/6 = 2/9. Explain the error and find the sum.",
                                  "answer": "Use sixths: 1/3 = 2/6, so 2/6 + 1/6 = 3/6 = 1/2. Adding denominators does not keep a common-sized unit.",
                                  "required": ["rename one third as two sixths", "sum is three sixths or one half", "denominator describes the common unit"]}]}]}
TOPIC_PREP = {"capability": GOAL, "environment": "Prepared presentation fixture; no model or external research is invoked.",
              "chunks": [{"id": "foundations", "label": "Units and representations", "nodes": ["parts", "equivalent", "numberline"]},
                         {"id": "application", "label": "Combine and explain", "nodes": ["add"]}],
              "exit_criteria": [EXIT], "sources": []}

TOUR = [
    {"title": "Save a question before waiting", "node": "parts", "stage": "question",
     "text": "The real ask command saves a pending question, its variant and rubric version. Reloading the browser does not lose it.",
     "say": "The chat is not the memory. The unanswered question already exists on disk."},
    {"title": "Separate an answer from its assessment", "node": "parts", "stage": "assessment",
     "text": "A prepared sample answer is saved with answer. It is not graded yet. In a normal lesson Claude assesses it; this demo supplies explicit sample assessments.",
     "say": "Saving what the learner said and deciding what it demonstrates are different operations."},
    {"title": "Record independent understanding", "node": "parts", "stage": "evidence",
     "text": "record applies an explicitly supplied passing assessment. Coverage becomes covered, readiness becomes ready, and the first review is scheduled for tomorrow.",
     "say": "The engine records evidence; it does not infer understanding from the answer text on its own."},
    {"title": "Ask about equivalent fractions", "node": "equivalent", "stage": "question",
     "text": "The prerequisite is now covered and ready. A second concept gets its own saved check.",
     "say": "The plan is a dependency graph, not simply a list of pages to get through."},
    {"title": "A mistake blocks the dependent branch", "node": "equivalent", "stage": "repair",
     "text": "A scripted misconception receives a failing assessment. Adding unlike fractions is blocked. The number-line branch remains eligible.",
     "say": "We can see the difference between having taught a concept and having evidence that it is understood."},
    {"title": "Keep the independent branch open", "node": "numberline", "stage": "evidence",
     "text": "The number-line check can still be completed because it depends on equal parts, not on the concept that needs repair.",
     "say": "One gap does not erase everything the learner can still do."},
    {"title": "Repair with a recorded hint", "node": "equivalent", "stage": "question",
     "text": "A repair question is saved, then hint records a nudge. Help becomes part of the evidence rather than being forgotten.",
     "say": "A correct answer after a hint is useful, but it is not the same as independent recall."},
    {"title": "Recover the pending interaction", "node": "equivalent", "stage": "resume",
     "text": "The actual SessionStart hook runs in a fresh process. Its output restores the same pending question and next action from saved files.",
     "say": "This is what survives a new session or a cleared conversation. It is a hook demonstration, not a restarted Claude session."},
    {"title": "A supported pass is provisional", "node": "equivalent", "stage": "evidence",
     "text": "The sample assessment requests quality 4, but the recorded nudge caps it at 2. Readiness becomes provisional and review remains due tomorrow.",
     "say": "The scheduling rules deliberately stop a helped answer from becoming evidence of independent recall."},
    {"title": "Apply the concept", "node": "add", "stage": "evidence",
     "text": "An independent passing check on addition supplies evidence for the application node. Provisional prerequisites are allowed by the current implementation.",
     "say": "Provisional is not the same as failed: the tutor may continue deliberately while retaining the need to revisit."},
    {"title": "Require an exit check", "node": "add", "stage": "complete",
     "text": "A prepared transfer question receives an independent passing assessment. Only then does the real finish command accept the topic as complete.",
     "say": "Completion has conditions. It still does not mean the material will never be forgotten."},
    {"title": "Advance only the demo clock", "node": "parts", "stage": "review",
     "text": "The sandbox clock moves one day forward using LEARN_NOW. A successful due review grows this card's interval from 1 day to 6 days.",
     "say": "We do not have to wait a week to demonstrate scheduling, and we do not change the computer's clock."},
    {"title": "Demonstrate longer-term recall", "node": "parts", "stage": "review",
     "text": "After another six simulated days, a quality-4 review grows the interval from 6 to 15 days. These are outputs from the actual scheduler.",
     "say": "The interval changes because of dated review evidence, not because the answer was repeated immediately."},
    {"title": "Forgetting changes retention, not history", "node": "equivalent", "stage": "review",
     "text": "A failed later review marks equivalent fractions as needs_review. Its coverage and readiness remain intact; downstream learning is not erased.",
     "say": "Taught, ready to build on, and remembered later are three separate judgments."},
]
