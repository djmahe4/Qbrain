# Week 7 — Test Generation: Invariant Verifier Agent

**Phase:** 4 (Test Generation)  
**PR Checkpoint:** `feat/invariant-verifier`

## Goals

- Implement the **Invariant Verifier Agent** that performs contrastive auditing against domain templates (LogicScan-style).
- Detect missing authorization checks, state-transition gaps, and business-rule violations.

## Detailed Tasks

1. **`brain/agents/invariant_verifier.py`**
   - Input: logic models (state machines, privilege matrices, candidate invariants) + enriched atoms.
   - Contrastive process:
     1. Load domain templates (E-commerce checkout, Password reset, Role delegation, DVWA modules, …).
     2. Align extracted state machine against template.
     3. Flag missing nodes (e.g., missing “authorize before mutate”), missing edges, or violated invariants.
   - Output: structured findings mapped to OWASP API Top 10 (BOLA, BFLA, …) and CWE-840 / CWE-284.

2. **Template library**
   - Start with 3–5 Markdown / JSON templates under `brain/templates/` or `skills/qbrain-domain-templates/`.
   - Templates are human-editable so analysts can extend them without code changes.

3. **Evidence linkage**
   - Every finding carries the parent hashes of the symbols that contributed to the gap.

## Acceptance Criteria

- [ ] On a deliberately broken fixture (missing auth gate), the verifier emits a BOLA / missing-check finding.
- [ ] Findings include CWE / OWASP mapping and source-symbol linkage.
- [ ] Templates are loadable and versionable.

## Deliverables

- Invariant Verifier Agent
- Initial domain template set
- PR `feat/invariant-verifier`
