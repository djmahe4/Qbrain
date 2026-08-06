# Architecture Overview — Skill-Driven Multi-Agent Pipeline

## Design Goals

1. **Graph-native, never text-search loops** — all structural lookups go through `codebase-memory-mcp`.
2. **Deterministic non-looping traversal** — DATG with state hash  
   \( h(s_t) = \mathrm{XXH3}(v_i \Vert \mathrm{sort}(P_t) \Vert \mathrm{sort}(\Theta_t)) \)  
   and Q-learning path penalization.
3. **Language & infra awareness at multiple levels** without bloating the main LLM context.
4. **Air-gapped** — local Ollama (Qwen-2.5-Coder / Llama-3) + local SQLite substrate.
5. **Business-logic first** — BOLA, CWE-840, workflow bypass, state-transition, privilege escalation.

## Agent Hierarchy

```
DATG Coordinator (owns visited-hash set + global Q-table)
│
├── Context Builder Agent          (Phase 2 entry)
│   ├── LanguageSubagent(php)      ← skill: qbrain-lang-php
│   ├── LanguageSubagent(python)   ← skill: qbrain-lang-python
│   ├── LanguageSubagent(js/ts)    ← skill: qbrain-lang-js
│   ├── LanguageSubagent(…)        ← additional language skills
│   └── InfraSubagent              ← skill: qbrain-infra
│
├── Logic Specifier Agent          (builds state machines & privilege matrices)
├── Invariant Verifier Agent       (contrastive checks vs domain templates)
└── Dynamic DAST Execution Agent   (multi-step stateful HTTP sequences)
```

## Multi-Level Enrichment Flow

| Level | Producer | Consumer | Payload |
|-------|----------|----------|---------|
| 0 | Context Builder (MCP only) | Language / Infra Subagents | Structural facts (symbols, callers, callees, endpoints) |
| 1 | Language Subagent + skill | Logic Specifier | Privilege atoms, framework hints, data-flow, genome |
| 2 | Infra Subagent | Logic Specifier + Invariant Verifier | Cross-service edges, env/OpenAPI privilege boundaries |
| 3 | Logic Specifier | Invariant Verifier + DAST | State machine, privilege matrix, invariants |
| 4 | Invariant Verifier | DAST | Missing-check / violation findings |
| 5 | DAST Agent | Evidence store + Obsidian | Stateful HTTP results + taint traces |

## Shared Substrate

- **File:** `<vault>/.qbrain/qmd.sqlite` (or `qbrain-mind-*.sqlite`)
- **Tables:** `agent_facts` (symbol, hash, payload JSON, created_at)
- **Protocol:** JSON-RPC 2.0 messages over the shared DB + optional stdio channels
- **Hash:** every agent state is hashed before action; collisions force backtrack

## Skill Packages (skill-creator format)

```
skills/
├── qbrain-lang-php/
│   └── SKILL.md          # Laravel Gate/Policy, DVWA, Symfony, plain PHP
├── qbrain-lang-python/
│   └── SKILL.md          # FastAPI Depends, Django permission_classes, Flask
├── qbrain-lang-js/
│   └── SKILL.md          # Express middleware, NestJS Guards
└── qbrain-infra/
    └── SKILL.md          # Docker Compose, K8s RBAC, OpenAPI securitySchemes, .env
```

Skills encode the non-obvious domain knowledge so subagents stay thin and the knowledge remains versionable and auditable.

## Relationship to Existing Code

| Existing | Role in new architecture |
|----------|--------------------------|
| `brain/indexer.py` | MCP CLI wrapper — used by Context Builder |
| `brain/language_parser.py` + `brain/parsers/*` | Base genome extractors — called by Language Subagent |
| `brain/cognitive_layer.py` | Precursor; will be superseded by DATG Coordinator |
| `brain/commands/audit.py` | Will invoke the full agent pipeline |

## Security & Compliance Notes

- Binary allow-list for MCP remains enforced.
- No source code leaves the air-gap (Ollama local only).
- All agent writes are append-only / replace-by-hash to the shared SQLite store.
