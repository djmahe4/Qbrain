# Week 2 — Foundation: Context Builder Agent + DATG Hashing

**Phase:** 1 (Foundation)  
**PR Checkpoint:** `feat/context-builder`

## Goals

- Implement the first primary agent: **Context Builder**.
- Enforce deterministic state hashing and basic Q-learning visit penalties.
- Expose the agent via CLI (`qbrain agent-context`).

## Detailed Tasks

1. **`brain/agents/context_builder.py`**
   - Class `ContextBuilderAgent` with:
     - `expand_node(symbol, depth)` — MCP-only lookups (`list_endpoints`, callers, callees, `trace_call_path`).
     - `bootstrap_entrypoints()` — discover and expand top-level surfaces.
     - `compute_hash()` implementing  
       \( h(s_t) = \mathrm{XXH3}(v_i \Vert \mathrm{sort}(P_t) \Vert \mathrm{sort}(\Theta_t)) \)
     - In-memory visited set + Q-table (positive reward on new node, penalty on revisit).
   - Never fall back to text search / `grep` / raw file reads for structure.

2. **JSON-RPC fact emission**
   - Every successful expansion writes a fact into `agent_facts` and returns a JSON-RPC 2.0 message.

3. **CLI command**
   ```bash
   uv run qbrain agent-context                 # bootstrap
   uv run qbrain agent-context SomeController  # single symbol
   ```

4. **Optional Ollama condensation**
   - If fact payload exceeds a token budget, call local Ollama to produce a short summary for downstream agents.

5. **Tests**
   - Mock MCP responses; assert hash stability, loop suppression, and DB write.

## Acceptance Criteria

- [ ] Context Builder uses only allowed MCP tools.
- [ ] Re-visiting the same (node, path, privilege) triple is rejected with a Q-penalty.
- [ ] Facts appear in `agent_facts` with a stable hash.
- [ ] CLI command returns structured JSON.
- [ ] Existing audit path remains green.

## Deliverables

- Full `ContextBuilderAgent` implementation
- CLI integration
- Unit + light integration tests
- PR `feat/context-builder`
