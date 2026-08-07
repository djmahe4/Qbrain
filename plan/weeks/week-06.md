# Week 6 — Model Construction: DATG Coordinator

**Phase:** 3 (Model Construction)  
**PR Checkpoint:** `feat/datg-coordinator`

## Goals

- Centralize traversal control in a **DATG Coordinator**.
- Own the global visited-hash set and Q-table; enforce non-looping rationalization across all agents.

## Detailed Tasks

1. **`brain/agents/datg_coordinator.py`**
   - Maintains:
     - Global `visited_hashes: Set[str]`
     - Global Q-table (node/transition → score)
   - Before any agent action: compute hash; reject or redirect if already visited.
   - Reward schedule:
     - +discovery for new structural node
     - +high reward for unverified logic transition / missing auth gate
     - −penalty for redundant tool call or already-evaluated node
   - Provides a simple scheduler that hands work to Context Builder → Language/Infra → Logic Specifier in topological order where possible.

2. **Integration**
   - Context Builder, Language Subagent, Logic Specifier all ask the coordinator for permission before acting and report outcomes for Q-updates.

3. **CLI**
   - `qbrain agent-run [--symbol S] [--max-nodes N]` — runs the coordinated pipeline.

## Acceptance Criteria

- [ ] Re-entrant expansion of the same state is blocked.
- [ ] Q-table values move in the expected direction under a controlled fixture.
- [ ] Coordinator can drive a small multi-symbol expansion without infinite loops.
- [ ] Existing single-agent CLI commands still work (coordinator is opt-in or behind the new command).

## Deliverables

- DATG Coordinator
- Coordinated CLI entry-point
- Loop-suppression tests
- PR `feat/datg-coordinator`
