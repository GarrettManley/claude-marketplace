---
name: council
description: Convene a four-voice council for ambiguous decisions, tradeoffs, and go/no-go calls. Use when multiple valid paths exist and you need structured disagreement before choosing. Not for code review, implementation planning, or architecture design.
version: 0.6.0
dependencies: []
---

> Adapted from `affaan-m/everything-claude-code` at commit [`4774946d`](https://github.com/affaan-m/everything-claude-code/blob/4774946db57a072f9b878f233a80f2ec6f5ac342/skills/council/SKILL.md) (MIT licensed). The anti-anchoring mechanism — fresh subagents that never see the conversation history — is the load-bearing technique.

# Council

Convene four advisors for ambiguous decisions:
- the in-context Claude voice (Architect + synthesizer)
- a Skeptic subagent
- a Pragmatist subagent
- a Critic subagent

This is for **decision-making under ambiguity**, not code review, implementation planning, or architecture design.

## When to Use

Use council when:
- a decision has multiple credible paths and no obvious winner
- you need explicit tradeoff surfacing
- the user asks for second opinions, dissent, or multiple perspectives
- conversational anchoring is a real risk
- a go / no-go call would benefit from adversarial challenge

Examples:
- monorepo vs polyrepo
- ship now vs hold for polish
- feature flag vs full rollout
- simplify scope vs keep strategic breadth

## When NOT to Use

| Instead of council | Use |
| --- | --- |
| Verifying whether output is correct | `superpowers:verification-before-completion` |
| Breaking a feature into implementation steps | `superpowers:writing-plans` |
| Designing system architecture | `feature-dev:code-architect` agent |
| Reviewing code for bugs or security | `pr-review-toolkit:code-reviewer` agent or `code-review:code-review` |
| Straight factual questions | just answer directly |
| Obvious execution tasks | just do the task |

## Roles

| Voice | Lens |
| --- | --- |
| Architect | correctness, maintainability, long-term implications |
| Skeptic | premise challenge, simplification, assumption breaking |
| Pragmatist | shipping speed, user impact, operational reality |
| Critic | edge cases, downside risk, failure modes |

The three external voices should be launched as fresh subagents with **only the question and relevant context**, not the full ongoing conversation. That is the anti-anchoring mechanism — and it is load-bearing. Sending the transcript defeats the point.

## Workflow

### 1. Extract the real question

Reduce the decision to one explicit prompt:
- what are we deciding?
- what constraints matter?
- what counts as success?

If the question is vague, ask one clarifying question before convening the council.

### 2. Gather only the necessary context

If the decision is codebase-specific:
- collect the relevant files, snippets, issue text, or metrics
- keep it compact
- include only the context needed to make the decision

If the decision is strategic/general:
- skip repo snippets unless they materially change the answer

If you need external reference material first (recent SOTA, prior art, citations): use `evidence:citation-seeker` to gather it BEFORE convening the council.

### 3. Form the Architect position first

Before reading other voices, write down:
- your initial position
- the three strongest reasons for it
- the main risk in your preferred path

Do this first so the synthesis does not simply mirror the external voices.

### 4. Launch three independent voices in parallel

Each subagent gets:
- the decision question
- compact context if needed
- a strict role
- no unnecessary conversation history

Prompt shape:

```text
You are the [ROLE] on a four-voice decision council.

Question:
[decision question]

Context:
[only the relevant snippets or constraints]

Respond with:
1. Position — 1-2 sentences
2. Reasoning — 3 concise bullets
3. Risk — biggest risk in your recommendation
4. Surprise — one thing the other voices may miss

Be direct. No hedging. Keep it under 300 words.
```

Role emphasis:
- **Skeptic:** challenge framing, question assumptions, propose the simplest credible alternative
- **Pragmatist:** optimize for speed, simplicity, and real-world execution
- **Critic:** surface downside risk, edge cases, and reasons the plan could fail

Dispatch the three in parallel (single message with three Agent tool uses). Use `general-purpose` as the subagent type unless a more specialized one fits the domain.

### 5. Synthesize with bias guardrails

You are both a participant and the synthesizer, so use these rules:
- do not dismiss an external view without explaining why
- if an external voice changed your recommendation, say so explicitly
- always include the strongest dissent, even if you reject it
- if two voices align against your initial position, treat that as a real signal
- keep the raw positions visible before the verdict

### 6. Present a compact verdict

Use this output shape:

```markdown
## Council: [short decision title]

**Architect:** [1-2 sentence position]
[1 line on why]

**Skeptic:** [1-2 sentence position]
[1 line on why]

**Pragmatist:** [1-2 sentence position]
[1 line on why]

**Critic:** [1-2 sentence position]
[1 line on why]

### Verdict
- **Consensus:** [where they align]
- **Strongest dissent:** [most important disagreement]
- **Premise check:** [did the Skeptic challenge the question itself?]
- **Recommendation:** [the synthesized path]
```

Keep it scannable on a phone screen.

## Persistence Rule

Do **not** write ad-hoc notes to `~/.claude/notes` or other shadow paths from this skill.

If the council materially changes the recommendation:
- use `remember` to capture the decision in session memory if it should survive a restart
- or update the relevant GitHub / Linear issue directly if the decision changes active execution truth
- or add a memory entry under `~/.claude/projects/<dir>/memory/` if the decision is durable user preference

Only persist a decision when it changes something real. Council that confirms the in-context position needs no persistence.

## Multi-Round Follow-up

Default is one round.

If the user wants another round:
- keep the new question focused
- include the previous verdict only if it is necessary
- keep the Skeptic as clean as possible to preserve anti-anchoring value

## Anti-Patterns

- using council for code review
- using council when the task is just implementation work
- feeding the subagents the entire conversation transcript
- hiding disagreement in the final verdict
- persisting every decision as a note regardless of importance
- launching the three subagents sequentially instead of in parallel (loses time, no anti-anchoring benefit)

## Related Skills

- `superpowers:verification-before-completion` — for "did we actually do the thing right" questions
- `superpowers:writing-plans` — once the decision is made and the work begins
- `evidence:citation-seeker` — gather external reference material before the council if needed
- `remember` — persist the decision delta if it changes durable state

## Example

Question:

```text
Should we adopt continuous-learning-v2 (instincts) as a new `learning@garrettmanley` plugin now, or wait until two more adoption stubs land first?
```

Likely council shape:
- Architect pushes for structural cohesion across the marketplace
- Skeptic questions whether instincts are actually solving a real pain point yet
- Pragmatist asks what the shortest path to first-instinct-captured is
- Critic focuses on storage location risk (`~/.claude` write-guard) and migration burden

The value is not unanimity. The value is making the disagreement legible before choosing.
