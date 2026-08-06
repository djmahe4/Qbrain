# Quant-BLM Business Logic Flow Analysis — Updated Project Plan

**Repository:** djmahe4/Qbrain  
**Branch target:** `main` (PR base)  
**Proposal source:** `qbrain-complete-guide.md` (original 12-week plan)  
**Architecture source:** `LLM Agent Architecture Research.md` + `.agents/skills/subagent-design`  

This directory contains the **updated 12-week implementation plan** that incorporates:

- Skill-driven **Language Subagents** (PHP, Python, JS/TS, …)
- **Infra Subagent** (Docker, OpenAPI, env, CI privilege edges)
- **Context Builder Agent** + full DATG pipeline with deterministic state hashing and Q-learning path penalization
- Multi-level enrichment feeding Logic Specifier → Invariant Verifier → Dynamic DAST agents
- Local Ollama reasoning and shared SQLite substrate (`qmd.sqlite`)

## Plan Structure

| File | Description |
|------|-------------|
| `README.md` | This overview |
| `00-architecture-overview.md` | High-level agent + skill architecture |
| `01-updated-timeline.md` | Master 12-week timeline (revised phases) |
| `weeks/week-01.md` … `week-12.md` | Detailed weekly plans with deliverables, acceptance criteria, and PR checkpoints |
| `PR_BODY.md` | Ready-to-paste GitHub PR description |
| `patches/` | Unified diffs for the agent/skill scaffolding |

## Key Changes from Original Proposal

| Original Phase | Updated Focus |
|----------------|---------------|
| Phase 1 Foundation (W1-2) | + MCP integration hardening, shared agent memory, Ollama bootstrap, skill-creator registry |
| Phase 2 Workflow Extraction (W3-4) | Context Builder Agent + Language Subagents + Infra Subagent; multi-level fact enrichment |
| Phase 3 Model Construction (W5-6) | Logic Specifier Agent produces state machines & privilege matrices from enriched atoms |
| Phase 4 Test Generation (W7-8) | Invariant Verifier + test-case synthesizer driven by DATG |
| Phase 5 Validation (W9-10) | Dynamic DAST Execution Agent with multi-step stateful HTTP sequences |
| Phase 6 Reporting (W11-12) | Obsidian/Mermaid export, open-source release, evaluation report |

## How to Use This Plan

1. Open `01-updated-timeline.md` for the executive view.
2. Work week-by-week from `weeks/week-XX.md`.
3. Each week ends with a concrete PR checkpoint that can be opened against `main`.
4. Skills live under a future `skills/` or `.qbrain/skills/` directory and are loaded by the subagents at runtime.
