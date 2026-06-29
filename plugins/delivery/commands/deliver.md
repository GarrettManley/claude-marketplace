---
name: deliver
description: Drive one body of work end-to-end through the delivery lifecycle — plan, adversarial plan review, subagent execution, completion gate, adversarial code review, land, retrospective — binding project-specific steps from .claude/delivery.local.md.
argument-hint: [<work-target>]
---

# /deliver

Deliver **$ARGUMENTS** (a directory like `@./some-app`, an issue reference, or a prose description;
if empty, ask the user what the body of work is) through the full delivery lifecycle.

Invoke the `deliver` skill and follow it exactly. It will:

1. Read `<repo>/.claude/delivery.local.md`, resolve the project slots, and **print the resolved-slot
   table** before anything else.
2. Run the lifecycle: pre-plan brief → write plan (+ project plan-writer) → doc cluster → adversarial
   plan review → approval → subagent execution → edit checklist → completion gate → adversarial code
   review → land → retrospective.

There are no flags — project behavior binds from the config file, not the command line. See the
`deliver` skill for the slot table, the config schema, and the landing policy.
