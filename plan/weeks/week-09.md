# Week 9 — Validation: Dynamic DAST Execution Agent

**Phase:** 5 (Validation)  
**PR Checkpoint:** `feat/dast-executor`

## Goals

- Implement the **Dynamic DAST Execution Agent** that runs multi-step stateful HTTP sequences against a live target.
- Provide a Docker-based DVWA (and optional custom microservice) harness.

## Detailed Tasks

1. **`brain/agents/dast_executor.py`**
   - Consumes test cases from the synthesizer.
   - Maintains session state (cookies, tokens, CSRF) across steps.
   - Records responses, status codes, and simple taint observations.
   - Marks each test as pass / fail / error against the expected outcome.
   - Writes results back to the evidence store and `agent_facts`.

2. **Docker harness**
   - `docker-compose.yml` (or extend existing) that brings up DVWA with known credentials and a minimal custom business-logic service (order / payment / admin endpoints with intentional flaws).
   - Health-check and seed scripts.

3. **Safety**
   - Only targets configured base URLs (localhost / docker network).
   - Rate limiting and timeout guards (CWE-400 awareness).

## Acceptance Criteria

- [ ] Executor can run a multi-step sequence against DVWA and report pass/fail.
- [ ] Session state is preserved across steps.
- [ ] Results are linked to the originating test-case and state-machine hashes.
- [ ] Harness starts cleanly with a single `docker compose up`.

## Deliverables

- DAST Execution Agent
- Docker compose + seed data
- PR `feat/dast-executor`
