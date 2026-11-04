# Reusable context and memory capabilities

Purpose: stop rediscovering the same tools in every AI software project. This file is a **candidate registry**, not an installation manifest, security certification, or permission to run outside code.

| Component | Canonical upstream | Role | Status |
| --- | --- | --- | --- |
| Context7 | https://github.com/upstash/context7 | Current library and framework documentation for coding agents | Optional development-time MCP |
| Graphify | https://github.com/Graphify-Labs/graphify | Local codebase knowledge graph and structured code/document search | Optional development-time skill; evaluate privacy controls |
| Graphiti | https://github.com/getzep/graphiti | Temporal graph memory | Research candidate, not required |
| Mem0 | https://github.com/mem0ai/mem0 | Memory extraction and retrieval | Research candidate |
| Letta | https://github.com/letta-ai/letta | Stateful agent memory | Research candidate |
| pgvector | https://github.com/pgvector/pgvector | Vector search on owned Postgres | Optional infrastructure |
| SQLite FTS5 | https://sqlite.org/fts5.html | Embedded lexical retrieval, no network | Preferred first local baseline |
| Stack Mutiny | https://github.com/BradKhan/bradkhan/tree/main/composable-internet/stack-mutiny | Task-specific skills discovery | Optional source selection layer |
| Mindport | https://github.com/BradKhan/mindport | Local-first portable context pack experiment | First consuming project |

## Required portability and provider neutrality

**A person's context must not depend on the model that generated or consumed it.** This is a baseline for all Open ASS-consuming projects, not a Mindport-only preference.

- Keep **canonical knowledge, source history, provenance, and approval scopes** independent of OpenAI, Anthropic, Google, xAI, hosted models, local models, and inference routers.
- Use explicit source/recipient adapters. No provider-specific object should become the canonical storage contract.
- Support human-inspectable, versioned JSON/JSONL (or other documented open formats) as a minimum interchange layer. User-approved context must remain exportable without an active API key.
- Keep models, graph/vector stores, indexing backends, agents, and synchronization providers replaceable behind typed interfaces.
- Never equate API message format compatibility with provider account-export compatibility. Verify actual formats with fixtures.
- Do not transmit private history as a side effect of searching, embedding, graphing, or model switching.
- For new adapters, test malformed input, provenance retention, select-before-disclose, and round-trip reimport in at least two environments where relevant.

The living implementation reference is [Mindport's interoperability contract](https://github.com/BradKhan/mindport/blob/feat/local-context-portability-mvp/docs/INTEROPERABILITY.md), currently under review in PR #7.

## Default use

1. Read Open ASS's `CONTEXT.md` and applicable stage route. Do not paste an entire project into agent context.
2. Query local project context and native documentation first. Use Context7 only when up-to-date third-party library APIs materially affect implementation.
3. For code relationships, compare existing grep and source maps against Graphify before installing it. Review its optional model-backed processing and data handling.
4. For user history, choose explicit import, consent and inspectable context extraction, not automatic graphification of private text.
5. Benchmark SQLite full-text lookup before adding graph or vector storage. Measure actual task accuracy, source attribution, token use, latency and privacy.
6. Pin exact upstream versions, verify licenses, inspect security and document integrations separately before promoting any candidate to `integrations/skills.lock.json`.
7. Keep all optional services replaceable. Never require a managed provider for a local baseline.

## Adoption and evidence

- Open ASS: implementation scaffolding, context routing, project verification, skill discovery and agent review.
- Venture Method: selectively applied product discovery, opportunity fit, decision records and adversarial assessment.
- Mindport: local text and conversation intake, user-approved context packs, JSONL/Markdown export, and a browser review interface; expanded provider-neutral adapters are under review.
- Skills are not packages: installing a skill file does not automatically install its runtime or validate performance.

When a component becomes verified in a real project, record the exact version, minimal usage, measured advantage over baseline, dependencies, failure mode and security boundary. Promote only after independent review.
