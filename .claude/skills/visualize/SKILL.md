---
name: visualize
description: Add one correct, minimal diagram to a lesson when an idea is genuinely clearer as a picture - a dependency graph, flow, sequence, state machine, tree, comparison, or a spatial/geometric figure. Delegates authoring and visual verification to a maker subagent, then embeds the result so it renders in the Obsidian note.
argument-hint: <what the picture must show>
---

# Visualize

A picture earns its place only when it shows something words cannot: shape, structure, direction, relationship, geometry. This skill produces one such picture, guarantees it is correct (the maker renders it and looks at it before returning), and drops it into the lesson so it renders in the note.

You are the creative director. You decide the exact idea and cut it to the fewest carrying elements. A maker subagent authors, renders, verifies and returns. You embed.

## When

Reach for a picture when the idea is a structure (dependencies, a system with parts and arrows, a pipeline, an exchange over time, states, a hierarchy, a containment) or is spatial (coordinates, a number line, vectors, the shape of a function, a physical arrangement). Do not visualize when prose or one equation already carries it. When in doubt, don't: a missing visual is cheaper than a false one.

## Choose the maker

- `mermaid-maker` for nodes and edges. Default. It returns Mermaid source; the note renders Mermaid natively, so you paste the source into your reply inside a ```mermaid fence.
- `svg-maker` for positions and shapes. It saves an SVG file into the vault's diagram folder and returns the filename; you embed `![[<file>.svg|500]]`.

## Brief the maker well

The most common failure is cramming. Before briefing, prune: for each element ask "if I delete this, is the idea still clear?" If yes, delete it. Give the concept and the concrete elements, not a vague topic and not a checklist. More than about 7 elements means cut first.

Bad: "make a diagram about how TCP works".
Good: "graph TD: a node 'packet' at the top; arrows down to 'ordering' and 'retransmit on loss'; both arrows down into 'reliable stream'. No title. Show that reliability is built FROM packets, not alongside them."

## Invoke

Use the Agent tool with `subagent_type` set to `mermaid-maker` or `svg-maker` and the brief as the prompt. The maker renders with `scripts/render.py`, looks at the PNG, iterates, and ends with a `RESULT:` block. Never hand-author or fake a diagram yourself; correctness depends on the render-and-inspect loop.

## Embed

- Mermaid: introduce the picture in one sentence, then the ```mermaid block with the returned source verbatim. Do not narrate every element back in prose.
- SVG: `![[<file>.svg|500]]`. The Stop hook mirrors your reply into the note, and Obsidian resolves the embed by filename because the diagram folder is inside the vault (see `vizDir` in `learn.config.json`).

If the maker returns `status: none`, simplify the brief or decide the picture is not worth it.
