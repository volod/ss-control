# Planning Workflow Guide

The documentation lifecycle keeps product intent, future work, and available behavior separate:

| Question | Source of truth |
| --- | --- |
| What should the product do? | [Specification](../design/spec.md) |
| What work remains? | [Implementation plan](../impl/plan.md) |
| What exists and where? | [Current implementation](../impl/current.md) |
| How should work be performed? | This guide and [AGENTS.md](../../AGENTS.md) |

## Task lanes

Use **Agent Implementation Tasks** when an agent can reach acceptance using repository fixtures,
deterministic tools, or an authorized non-interactive run:

- `CLEAR`: code, tests, and docs can finish locally.
- `RUN NEEDED`: implementation is deterministic, but acceptance includes a declared heavier run
  (Docker stack, local pipeline run, multi-arch image build).

Use **Human-Assisted Tasks** when acceptance itself needs a person or an authority unavailable to
an agent:

- `BLOCKED BY HUMAN`: an agent prepares support, but a human-provided artifact gates completion.
- `HUMAN-GATED`: the outcome is human judgment, authorization, private access, or spend approval.

Add `Research: yes` when the path is uncertain and a well-supported negative result is acceptable.

## Dependencies

The `Dependencies` field names other tasks by their backticked ids. Every id named before the
first of these markers is a start prerequisite: `Optional:`, `Cross-lane note:`, or `Blocks:`.
Write `none.` when a task has no prerequisites.

## Task shape

```markdown
### Capability name -- `capability-id`

#### stable-task-id

Describe the unresolved operator problem in present or future tense.

- Serves: `capability-id` -- [Specification section](../design/spec.md#section)
- Agent status: CLEAR
- Dependencies: none.
- User-visible outcome: State what becomes possible or trustworthy.
- Scope boundary: State what is in scope and explicitly out of scope.
- Data and artifact paths: Name repository-relative or `$DATA_DIR` locations.
- Execution path: Name modules, fixtures, commands, and any declared run.
- Acceptance gates: State deterministic checks and the negative-result rule.
- Documentation target: The current-state page that receives the result.
```

Human-lane tasks add a `Human step` line after `User-visible outcome`.

## Checks

| Command | What it enforces |
| --- | --- |
| `make lint-spec-plan` | Registry rows, task fields, lane statuses, group order, dependencies |
| `make lint-doc-links` | Relative links and heading anchors |
| `make plan-status` | Task counts and the next eligible task per lane |
