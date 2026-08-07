# Week 5 — Model Construction: Logic Specifier Agent

**Phase:** 3 (Model Construction)  
**PR Checkpoint:** `feat/logic-specifier`

## Goals

- Implement the **Logic Specifier Agent** that consumes enriched atoms and produces declarative business-logic models.
- Export state machines and privilege matrices to SQLite + Obsidian (Mermaid).

## Detailed Tasks

1. **`brain/agents/logic_specifier.py`**
   - Input: enriched facts (privilege atoms, data-flow, framework hints, call paths).
   - Output:
     - Workflow graph (nodes = operations, edges = valid transitions with pre/post conditions)
     - Privilege matrix (role → permitted operations)
     - State machine (valid application states + transitions)
     - Candidate invariants (“order total == sum(line items)”, “payment must precede fulfillment”, …)

2. **Storage & visualization**
   - Persist models under `agent_facts` (type = `logic_model`) and as Behavior JSON sidecars (existing Qbrain convention).
   - Generate Mermaid state diagrams and privilege-matrix tables for the Obsidian vault.

3. **Ollama assistance (optional)**
   - For complex control flow, ask local Ollama to propose missing transitions or invariants; keep human-auditable Markdown.

4. **Tests**
   - Synthetic e-commerce / DVWA workflow → assert state machine contains expected happy-path and at least one negative edge.

## Acceptance Criteria

- [ ] Logic Specifier produces a state machine that can be rendered as Mermaid.
- [ ] Privilege matrix maps at least two roles to distinct operation sets for the fixture.
- [ ] Models are queryable and linked back to source symbols via parent hashes.
- [ ] Vault sync shows the new diagrams.

## Deliverables

- Logic Specifier Agent
- Mermaid / JSON export path
- PR `feat/logic-specifier`
