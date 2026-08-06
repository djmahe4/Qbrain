# Week 8 — Test Generation: Multi-Step Test Synthesizer

**Phase:** 4 (Test Generation)  
**PR Checkpoint:** `feat/test-synthesizer`

## Goals

- Generate both positive and negative multi-step HTTP test sequences from the verified state machines.
- Produce payloads that can be executed by the DAST agent.

## Detailed Tasks

1. **`brain/agents/test_synthesizer.py`**
   - Walk the state machine:
     - Happy-path sequences (all required steps in order).
     - Bypass sequences (skip a required step).
     - Privilege sequences (role A attempts role B operations).
     - Parameter-tampering sequences (immutable fields, price, user-id, …).
   - Emit structured test cases:
     ```json
     {
       "id": "...",
       "steps": [{"method": "POST", "path": "...", "body": {...}, "headers": {...}}, ...],
       "expected": {"status": 403, "invariant": "payment_before_fulfillment"},
       "cwe": ["CWE-840"],
       "owasp": ["API1:2023"]
     }
     ```

2. **Storage**
   - Persist under `agent_facts` (type = `test_case`) and as YAML/JSON sidecars for human review.

3. **Optional Ollama**
   - Assist in generating realistic request bodies from OpenAPI or form schemas discovered by Infra Subagent.

## Acceptance Criteria

- [ ] Synthesizer produces ≥ 1 happy-path and ≥ 2 negative sequences for the e-commerce / DVWA fixture.
- [ ] Each test case references the state-machine edges it exercises.
- [ ] Output is consumable by the DAST executor (Week 9).

## Deliverables

- Test Synthesizer Agent
- Example test-case library
- PR `feat/test-synthesizer`
