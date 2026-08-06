# Updated 12-Week Timeline

Source baseline: `qbrain-complete-guide.md` §6.3  
Revision: skill-driven Language/Infra Subagents + full DATG multi-agent pipeline.

| Week | Phase | Focus | Primary Deliverables | PR Checkpoint |
|------|-------|-------|----------------------|---------------|
| 1 | Foundation | MCP hardening, shared agent memory, Ollama bootstrap, skill-creator registry | `qmd.sqlite` schema, Config extensions, skill loader skeleton | `feat/agent-foundation` |
| 2 | Foundation | Context Builder Agent + deterministic state hashing + Q-table | `brain/agents/context_builder.py`, CLI `agent-context` | `feat/context-builder` |
| 3 | Workflow Extraction | Language Subagent core + first skill (`qbrain-lang-php`) | `brain/agents/language_subagent.py`, `skills/qbrain-lang-php/` | `feat/lang-subagent-php` |
| 4 | Workflow Extraction | Remaining language skills + Infra Subagent | `qbrain-lang-python`, `qbrain-lang-js`, `qbrain-infra` | `feat/lang-infra-skills` |
| 5 | Model Construction | Logic Specifier Agent — state machines & privilege matrices | `brain/agents/logic_specifier.py`, Mermaid export | `feat/logic-specifier` |
| 6 | Model Construction | DATG Coordinator + global visited-hash set + Q-learning penalization | `brain/agents/datg_coordinator.py` | `feat/datg-coordinator` |
| 7 | Test Generation | Invariant Verifier Agent (contrastive domain templates) | `brain/agents/invariant_verifier.py`, template library | `feat/invariant-verifier` |
| 8 | Test Generation | Multi-step test-case synthesizer driven by state machines | `brain/agents/test_synthesizer.py` | `feat/test-synthesizer` |
| 9 | Validation | Dynamic DAST Execution Agent + Docker DVWA harness | `brain/agents/dast_executor.py`, docker-compose | `feat/dast-executor` |
| 10 | Validation | End-to-end evaluation on DVWA + custom e-commerce testbed | Metrics report, false-positive analysis | `feat/eval-dvwa` |
| 11 | Reporting | Obsidian/Mermaid polish, privilege-matrix views, evidence store | Vault templates, CLI polish | `feat/obsidian-polish` |
| 12 | Reporting | Final report, open-source release notes, documentation | `docs/`, CHANGELOG, evaluation MD | `release/v0.2.0` |

## Phase Mapping (Original → Updated)

| Original (MD) | Updated Emphasis |
|----------------|------------------|
| Phase 1 Foundation (W1-2) | Agent substrate + Context Builder + skill registry |
| Phase 2 Workflow Extraction (W3-4) | Multi-level enrichment via Language + Infra Subagents |
| Phase 3 Model Construction (W5-6) | Logic Specifier + DATG Coordinator |
| Phase 4 Test Generation (W7-8) | Invariant Verifier + test synthesizer |
| Phase 5 Validation (W9-10) | DAST Execution Agent + evaluation |
| Phase 6 Reporting (W11-12) | Vault, docs, release |

## Success Criteria (Project Level)

- [ ] Context Builder never falls back to text-search / grep loops
- [ ] Every agent action is gated by DATG state hash; loops are suppressed
- [ ] Language Subagents inject framework-specific privilege atoms for at least PHP, Python, JS/TS
- [ ] Infra Subagent surfaces cross-service and env-based privilege edges
- [ ] Invariant Verifier detects at least the classic BOLA / workflow-bypass patterns in DVWA + custom testbed
- [ ] Full pipeline runs air-gapped with local Ollama
- [ ] All artifacts sync to Obsidian Vault as Mermaid state diagrams + privilege matrices
