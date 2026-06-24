Date: <YYYY-MM-DD>
Author(s): <Name(s)>
Version: 0.1 (Draft)

# <Component or Feature Name> — Design Document

# Introduction

## Purpose

<One paragraph: what problem this design solves, why it matters, who reads this document.>

## Scope

**In scope:** <list of components, behaviors, environments covered>

**Out of scope:** <list of items reviewers might expect but won't find here — point them at the right doc instead>

## Definitions and Acronyms

<Include only if 3 or more project-specific terms are introduced. Otherwise delete this section.>

| Term | Definition |
|------|------------|
| <Term> | <Definition> |

# Overview

<2–4 sentences: the design at a glance. Reader should leave this section knowing what the system does, where it sits in the larger architecture, and the key decisions. No diagrams here yet.>

# System Overview

<Diagram showing components and their relationships. Use Mermaid. Match the fencing to your renderer.>

```mermaid
flowchart LR
    A[Client] --> B[This Component]
    B --> C[Downstream Service]
```

## Components

- **<Component A>** — <responsibility>
- **<Component B>** — <responsibility>

# Architecture / Design Details

<The substantive section. Per-component design, key data structures, control flow, configuration surfaces. Use sub-headings (`##`) per component. Lead each sub-section with a one-sentence "what this component does and why it exists.">

# Execution Flow

<Sequence diagram or numbered steps showing the end-to-end happy path. Add a second one for the most important error path.>

# Dependencies

| Dependency | Type | Version / Pinning | Why we need it |
|------------|------|-------------------|----------------|
| <name> | <library / service / spec> | <version> | <one line> |

# References

- <Spec / ADR / prior design doc — link>
- <External standard — link>

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1 | <YYYY-MM-DD> | <Author> | Initial draft |
