# Open ASS delegation architecture, v1

Status: **experimental adapter and contract**, not an autonomous multiagent platform. Decision record for [#48](https://github.com/BradKhan/open-ASS/issues/48). Based on the existing [supervisor](../scripts/supervisor.py), [dispatcher](../scripts/dispatch.py), [lifecycle](../scripts/lifecycle.py), and [harness adapter](../scripts/harness.py).

## Design decision

Build **one reusable engineering contract**, with a small delegation interface over the existing supervised run machinery. Do not replace native agent teams, reinvent a second scheduler, or require a hosted model, cloud provider, GitHub, or retrieval engine for local planning.

```text
Human/project authority (issue + acceptance + policy)
      |
      v
Open ASS delegation request (versioned JSON, scope, budget, provenance)
      |
      v
Deterministic validation (provider allowlist, depth, scope, time, money)
      |
      +----> CLI/native Codex, Claude, Hermes (current adapters)
      +----> ACP, external Delegate, A2A, other runners (future adapters)
      |
      v
Existing local supervisor (leases, output bounds, cancel/recovery, optional OCI)
      |
      v
Execution receipt -> project tests -> exact-head CI -> authorized acceptance
```

**Authorization is not a property of a JSON file.** The parent grant is a requested ceiling, not evidence that the grant came from a trusted actor. The host, configured sandbox, durable task, owner and GitHub rulesets enforce authority. No new contract field can bypass those controls.

## V1 wire contract

See [machine-readable schema](../contracts/delegation.v1.schema.json). Example:

```json
{
  "schema": "openass.delegation.v1",
  "id": "delegate-001",
  "parent": {
    "id": "parent-001",
    "permission": "workspace-write",
    "providers": ["codex", "claude"],
    "scopes": ["src", "docs"],
    "budget_cents": 200,
    "timeout_seconds": 900,
    "max_depth": 2
  },
  "child": {
    "task_id": "child-001",
    "harness": "codex",
    "role": "engineer",
    "permission": "workspace-write",
    "scopes": ["src/example.py"],
    "budget_cents": 50,
    "timeout_seconds": 180,
    "depth": 1,
    "criteria": "Implement and independently test the accepted behavior.",
    "context": [{"path": "docs/plan.md", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]
  }
}
```

```bash
python3 scripts/openass.py delegate providers
python3 scripts/openass.py delegate plan delegation.json
python3 scripts/openass.py delegate plan delegation.json --db /absolute/path/to/tasks.sqlite
python3 scripts/openass.py delegate run delegation.json --db /absolute/path/to/tasks.sqlite --actor worker
# Real execution is opt-in, uses the *existing* supervisor:
python3 scripts/openass.py delegate run delegation.json --db /absolute/path/to/tasks.sqlite \
  --actor worker --execute --ack-unmetered --backend container \
  --container-image example/image@sha256:ACTUAL_VERIFIED_DIGEST
```

The child task must already exist in the lifecycle database, be `ready`, and have acceptance criteria exactly matching the delegation request. The child budget must be within the remaining durable task allocation. A review-only request can be planned but **cannot execute through the writable supervisor**.

`plan` makes **no calls to a model** and creates no task. It prints a deterministic, inspectable request summary. `providers` reports installed binary locations, not authentication or runtime assurance.

## Isolation and authority

- Parent `read-only` cannot produce a child `workspace-write` request.
- Allowed provider, relative scopes, depth, maximum timeout and allocation must be subsets of the parent declaration.
- Unknown fields, shell arguments, absolute/traversing paths, invalid digests and unsupported providers fail closed.
- Context references are independently re-hashed immediately before an opted-in launch. Verified files are passed into the existing ICM stage bundle with the role-appropriate stage instructions. This is not a guarantee that the model read or correctly interpreted every source.
- **Scopes are validated but not yet enforced at the filesystem or network layer.** An operating-system sandbox is required for that guarantee. This includes the case where an underlying provider has native write access beyond its advertised workspace.
- Containers are optional. The existing container backend requires a digest-pinned image and disallows network, with bounded resources.
- No approval, merge, deployment, external tool installation, account linking, provider authentication or automatic follow-up is performed by the delegation adapter.
- Cost reservations are not actual billing ceilings. Provider usage is recorded when available; other providers may exceed reservations.

## OKF and ICM integration

- **ICM** is already the canonical context router (`context/routes.json` and `scripts/context.py`). A delegated role maps to its existing ICM stage. At actual execution, requested context references are hashed and supplied as working files to the stage's bounded context bundle.
- **OKF v0.2** is an optional, human-readable knowledge source, not another mandatory memory database. Run `python3 scripts/openass.py okf inspect path/to/bundle` to inspect documents, their real SHA-256 hashes, and available provenance metadata. Add an explicit `project_context_path` and `sha256` from a project-local bundle to the child context in the delegation contract.
- Bundle inspection requires only `PyYAML==6.0.3`, installed explicitly using `pip install -r requirements-okf.txt`; the ordinary Open ASS CLI keeps its existing minimal runtime dependencies. Development CI installs the same pin for tests.
- The OKF reader performs **bounded structural checks**, not complete certification of every v0.2 semantic rule. It does not execute attesters, infer verified trust, fetch external sources, or import any knowledge automatically.
- OKF stores portable knowledge, ICM scopes its use, the delegation contract requests bounded execution, and the existing verifier/authorization system decides what may be accepted. No layer gives another layer authority by adding metadata.

## Interfaces to standardize next

| Concern | External interface | Why it remains separate |
| --- | --- | --- |
| Agent session/continuation | ACP stable v1 (v2 experimental) | Interactive session semantics differ by runtime |
| Tool and context access | MCP 2026-07-28 with negotiation | Tool authorization belongs to host, not prompt text |
| Remote agent collaboration | A2A where independently deployed | Avoid requiring A2A for same-host subagents |
| Reusable skills | Agent Skills + audited manifests | Skills are untrusted instructions, not permissions |
| Specialized delegation backend | [Delegation Layer](https://github.com/hishamkaram/delegation-layer) | Compare real guarantees, cost and failure behavior before integration |
| Code/document retrieval | XERJ / local FTS / search adapters | Retrieval cannot grant authority or silently upload private code |
| Accepted changes | Git + source control adapters | GitHub is one configured authority; portability requires equivalent backends |

References: [Anthropic multiagent patterns](https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration), [ACP protocol](https://agentclientprotocol.com/), [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28), [Delegation Layer security](https://github.com/hishamkaram/delegation-layer/blob/main/docs/security.md).

## Acceptance and negative cases

1. Versioned schema readable without a particular model SDK.
2. Role, provider, scope, budget, timeout, and depth decisions are deterministic.
3. Explicit initial user action for every real execution, with no model usage on dry run.
4. Existing lifecycle is the only source of task state; no duplicate queue/database.
5. Unknown capabilities cannot be silently substituted with another agent.
6. Every result remains `accepted: false` until separately reviewed and verified.
7. Regression tests explicitly document currently unenforced claims.

## Next work on #48

**Before parallel workers:** establish host-enforced per-child scopes, subtask identity/lease fencing, shared parent budget reservations, isolated worktrees/OCI, cancellation propagation, and bounded result collection.

**Before native session continuation:** validate actual ACP/native version behavior, session identity, resumability, prompt and context isolation, refusal on unsupported capabilities, and redacted transcripts.

**Before public interoperability claims:** end-to-end evidence across at least three runtimes and a second code-host backend; include failure-injection cases and explicit version matrix.
