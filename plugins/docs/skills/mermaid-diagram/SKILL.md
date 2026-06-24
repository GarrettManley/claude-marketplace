---
name: mermaid-diagram
description: Use when creating or editing Mermaid diagrams in documentation — wiki pages, design docs, architecture docs, READMEs. Provides a configurable brand palette, semantic color roles, renderer-agnostic fencing, and common-mistake guidance.
version: 0.1.0
dependencies: []
---

# Mermaid Diagrams

Brand-consistent Mermaid diagrams with a small, semantic color palette and renderer-agnostic fencing. Light pastel fills with saturated strokes — readable in both light and dark themes.

## When to use

- Embedding a flowchart or sequence diagram in a design doc, architecture doc, wiki page, or README.
- Choosing fencing for a target renderer (GitHub/GitLab triple-backtick vs Azure DevOps Wiki triple-colon).
- Picking colors: map every styled node to one of the three semantic roles instead of inventing fills.

## Fencing — check your renderer

Most Markdown renderers expect triple-backtick fencing:

````
```mermaid
flowchart TD
    A --> B
```
````

Some renderers (notably **Azure DevOps Wiki**) need triple-colon fencing instead:

```
::: mermaid
flowchart TD
    A --> B
:::
```

If your diagram renders as code instead of a diagram, swap the fencing.

## Color Palette — semantic roles

Three roles. Every styled node gets one of them. The default palette below is a neutral pastel set; replace with your project's brand colors by editing the table in your project-local fork.

| Role | Fill | Stroke | Use for |
|------|------|--------|---------|
| Enforcement | `#fce4cc` | `#c0570d` | Security gates, rejection points, caution/wait states. Nodes where a request is accepted or denied. |
| Processing | `#dae8cd` | `#38571a` | Application logic, validation steps, transformations. Active components that operate on data. |
| Infrastructure | `#cbebfa` | `#144c8f` | Stores, caches, routing, shared services. Supporting plumbing. |

Text color is always `#1a1a1a` for legibility against pastel fills.

### Configuring your own palette

To brand-match a project, fork this skill into the project's `.claude/skills/mermaid-diagram/` and replace the three role rows with your tokens. Keep the **semantic roles** stable — color is meaning, not decoration.

## Flowchart Node Styling

Use per-node `style` directives (not `classDef`):

```
style NodeId fill:#fce4cc,stroke:#c0570d,color:#1a1a1a
style NodeId fill:#dae8cd,stroke:#38571a,color:#1a1a1a
style NodeId fill:#cbebfa,stroke:#144c8f,color:#1a1a1a
```

Only style nodes that benefit from color. Default (unstyled) nodes are fine for external actors, start/end terminals, and simple decision diamonds.

## Sequence Diagrams

Leave unstyled. Mermaid defaults produce readable black-on-white participant boxes. Sequence diagrams communicate through structure (participants, message flow, alt blocks), not color. Custom theme overrides (`%%{init:}%%`) cause readability problems across light/dark rendering environments.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Dark fills with white text (`fill:#0F4C81,color:#fff`) | Use light pastel fills with dark text. Dark fills fail in dark mode. |
| Inventing colors not in the role table | Use only the three semantic roles. Map every color back to one of them. |
| Styling every node | Only style nodes where color adds meaning. Leave external actors and terminals unstyled. |
| Using `classDef` + `:::className` | Use per-node `style` directives for explicitness and portability. |
| Wrong fencing for the renderer | GitHub/GitLab/most wikis: triple-backtick. ADO Wiki: `:::mermaid` / `:::`. Test once and pick. |
| Custom theme on sequence diagrams | Mermaid base theme creates dark backgrounds. Leave sequence diagrams unstyled. |
| Using `\n` for line breaks in node/edge labels | Use `<br>` instead. Many Mermaid renderers display `\n` as literal text. |
