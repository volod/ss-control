# Task Record

Copy to `NNNN-<group>-<task-id>.md` using the naming rules in the
[planning workflow](../../guide/planning-workflow.md), index it in the
[records README](README.md), and replace this paragraph with the task title.

## Task and scope

- Id / capability: `task-id` / `capability-id`
- State: active, blocked, or accepted (only after every required gate passes).
- Source: plan task or ad hoc request; commit at start and any unrelated dirty files.
- Plan counts at start: open tasks (agent, human) and the next eligible task per lane.
- Accepted task: the full original block, verbatim, in a fenced Markdown block.
- Amendments: none, or each revised block with its reason and who authorized it.

## Implementation

Changed modules and behavior, reused code, decisions and rejected alternatives.

## Acceptance evidence

| Gate | Exact command, test or artifact | Result and limit |
| --- | --- | --- |
| Each acceptance gate | Reproducible evidence | pass, fail, not-run, blocked or valid-negative |

## Audit handoff

`none identified` with the reviewed scope, or one entry per finding.

## Close or resume

Gates passed and remaining, the next action, and capability status changes.
