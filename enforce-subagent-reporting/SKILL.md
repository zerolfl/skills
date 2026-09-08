---
name: enforce-subagent-reporting
description: "Adjust subagent instructions by preserving their domain-specific behavior while enforcing one-shot status reporting. Use when creating or revising a subagent instruction, not when dispatching an ordinary task to an already-configured subagent."
---

# Enforce Subagent Reporting

Act as a design-time instruction adjuster. Preserve the target subagent's role and specialist behavior; add only the reporting protocol below and changes needed to remove conflicts.

## Activation Boundary

Apply this skill only while creating, revising, or reviewing the subagent's persistent instruction. It defines behavior for the target subagent; it does not define the parent agent's behavior and is not a prompt to repeat on every task dispatch.

After the target instruction contains the protocol, a normal dispatch message should include only the task-specific scope, inputs, expected work, and role-specific evidence needs. Do not paste or restate the status-line, one-shot-return, or blocker protocol in that message. Repeat it only when the target runtime does not load the adjusted instruction or the user explicitly requests repetition.

## Scope

1. Read the proposed or existing subagent instruction, not an individual task message.
2. Keep its role, workflow, tools, permissions, validation rules, and specialist output details.
3. Merge in the required protocol and resolve only direct or implicit conflicts.
4. Return or save the adjusted instruction as requested; do not rewrite ordinary dispatch messages unless explicitly asked.

Do not infer requirements from other subagents. Do not add generic role design, tool policy, workflow, evidence fields, or configuration guidance unless requested.

## Required Protocol

Insert or adapt this block in the target instruction only. Do not copy it into ordinary task-dispatch messages. Keep its semantics unchanged:

```text
Mandatory final-reporting protocol:
1. The first line of the final response must be exactly one selected value: `status: complete`, `status: partial`, or `status: blocked`. Put no title, greeting, code fence, Markdown marker, or other text before it. Use `complete` only when all requested work and verification are finished; use `partial` for meaningful work with non-blocking gaps; use `blocked` when safe or authorized continuation is impossible, even if partial work exists.
2. Use terminal-only communication. During execution, do not send progress, stage reports, partial results, ordinary status messages, or other intermediate messages to the delegating agent. Keep intermediate findings inside this task and return exactly once through the final-response mechanism. If the host names it `FINAL_ANSWER`, emit exactly one `FINAL_ANSWER` and no preceding `MESSAGE`.
3. On any blocker, error, permission restriction, safety risk, failed validation, missing dependency, unavailable external state, or inability to complete, stop immediately. Explain the reason and required next action only in the single final response.
4. When reading or modifying files, include verifiable `file:line` references for key conclusions, actual changes, unfinished items, and failure reasons. Use line numbers from the modified file's final state, or from the final inspected state for a read-only file. Never guess line numbers; if reliable lines cannot be obtained, state that explicitly.
```

After the status line, retain the target role's appropriate compact and verifiable output format. Do not impose a new common body schema.

## Conflict Rules

- Rewrite progress reports, discovery reports, or `report before continuing` steps as internal checkpoints included only in the final response.
- Remove exceptions such as `normally`, `unless necessary`, or `prefer not to send messages` when they permit intermediate communication.
- If structured output must be JSON, fenced, or otherwise formatted, place it after the mandatory status line and preserve its role-specific fields.
- If the instruction says to ask the delegating agent when blocked, make the subagent stop and put the question or next action in the single `status: blocked` response.
- Preserve existing evidence requirements; for file-related work, ensure the required `file:line` references cover conclusions, changes, unfinished items, and failures.
- Do not weaken higher-priority host, system, safety, permission, or confirmation rules.

## Adjustment Workflow

1. Locate the target instruction's communication, progress, error-handling, and final-output clauses.
2. Insert the required protocol once, merging or removing conflicting duplicates.
3. Preserve all non-conflicting specialist instructions.
4. Check that nothing permits intermediate messages or content before the status line.
5. Check that the parent agent's dispatch template does not redundantly restate the protocol.
6. Deliver the adjusted instruction, not a summary of unrelated agents.

## Final Check

Verify that the adjusted instruction:

- preserves the original role and specialist behavior;
- requires one actual status line and one final response;
- terminates immediately on blockers;
- requires `file:line` evidence for file-related conclusions, changes, unfinished items, and failures;
- uses final-state or final-inspection line numbers without guessing;
- places structured output after the status line;
- keeps the protocol out of ordinary parent-to-subagent task messages;
- adds no unrelated conventions or schemas.

Apply this protocol to the target subagent instruction only. Do not impose it on the parent agent's own response unless explicitly requested.
