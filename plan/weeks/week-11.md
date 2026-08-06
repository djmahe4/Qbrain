# Week 11 — Reporting: Obsidian Polish & Evidence UX

**Phase:** 6 (Reporting)  
**PR Checkpoint:** `feat/obsidian-polish`

## Goals

- Make the agent outputs first-class citizens in the Obsidian vault.
- Improve privilege-matrix and state-machine views for human analysts.

## Detailed Tasks

1. **Vault templates**
   - Pages for:
     - Agent run summary (hashes, Q-table snapshot, findings count)
     - Privilege matrix (role × operation table)
     - State machine (Mermaid)
     - Individual findings with back-links to source symbols
   - Safe-escaped Mermaid (existing Qbrain practice).

2. **CLI polish**
   - `qbrain library sync` includes agent artifacts.
   - Optional `qbrain agent-report` that prints a human-readable summary.

3. **Evidence store**
   - Ensure all agent writes are queryable and durable under `.qbrain/`.

## Acceptance Criteria

- [ ] After a full agent run + `library sync`, the vault contains navigable Mermaid diagrams and privilege matrices.
- [ ] Findings are back-linked to symbols.
- [ ] No vault clutter outside the `.qbrain/` and designated folders.

## Deliverables

- Updated vault templates and sync logic
- CLI report command
- PR `feat/obsidian-polish`
