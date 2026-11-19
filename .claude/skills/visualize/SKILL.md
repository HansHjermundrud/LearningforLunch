---
name: visualize
description: Adds one minimal, verified diagram to a lesson when the idea really is easier to grasp as a picture - a dependency or precedence graph, a flow or sequence, a state machine, a tree, a side-by-side comparison, or a spatial or geometric figure. A maker subagent draws and visually checks it; the result is embedded so the Obsidian note renders it.
argument-hint: <what the picture must show>
---

# Visualize

Use a picture only for what text conveys badly: structure, shape, direction, relations between parts, geometry. This skill gets one such picture made, checked (the maker renders it and inspects the image before handing it back) and placed in the lesson, where the note renders it.

You set the brief: pick the one idea and strip it down to the elements that carry it. A maker subagent writes, renders and checks the picture. You put it into the lesson.

## When

Use one when the idea has structure (a dependency or precedence graph, components connected by arrows, a pipeline, messages exchanged over time, states, a hierarchy, nesting) or is spatial (a coordinate system, a number line, vectors, a function's graph, a physical layout). Skip it when a sentence or a single equation does the job. If unsure, leave it out: no picture costs less than a wrong one.

## Choose the maker

- `mermaid-maker`, the default, for anything made of nodes and edges. It hands back Mermaid source; paste it into your reply inside a ```mermaid fence and the note renders it.
- `svg-maker` when exact position or shape matters. It writes an SVG file into the vault's diagram folder and hands back the filename; embed it with `![[<file>.svg|500]]`.

## Writing the brief

Overcrowding is what usually goes wrong. Trim before you brief: for each element, would the point survive without it? If so, remove it. Name the idea and the specific elements, not a broad subject and not a feature list. If you count more than about 7 elements, trim first.

Weak brief: "draw a diagram about serializability".
Strong brief: "graph LR: nodes 'T1', 'T2', 'T3'; arrow T1 -> T3 labelled 'r1(x) before w3(x)'; arrow T2 -> T3 labelled 'w2(y) before r3(y)'. No title. Show that T3 must come after both, while T1 and T2 have no order between them."

## Invoke

Call the Agent tool with `subagent_type` `mermaid-maker` or `svg-maker` and the brief as the prompt. The maker renders through `scripts/render.py`, inspects the PNG, revises, and finishes with a `RESULT:` block. Do not write or imitate a diagram yourself: it is only trustworthy because the maker rendered and inspected it.

## Embed

- Mermaid: one sentence saying what the picture shows, then a ```mermaid block containing the returned source unchanged. Don't walk through the elements again in prose.
- SVG: `![[<file>.svg|500]]`. The Stop hook copies your reply into the note, and since the diagram folder lives inside the vault, Obsidian finds the file by name (see `vizDir` in `learn.config.json`).

If the maker returns `status: none`, make the brief simpler or drop the picture.
