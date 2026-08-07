# Week 10 — Validation: End-to-End Evaluation

**Phase:** 5 (Validation)  
**PR Checkpoint:** `feat/eval-dvwa`

## Goals

- Run the full pipeline (Context Builder → … → DAST) on DVWA and the custom business-logic testbed.
- Collect metrics and perform false-positive / false-negative analysis.

## Detailed Tasks

1. **Evaluation runs**
   - DVWA modules that exercise authorization / session / workflow (wherever applicable).
   - Custom e-commerce testbed with planted flaws:
     - Order price manipulation
     - Discount stacking / workflow bypass
     - Horizontal privilege escalation (BOLA)
     - Missing step (payment before fulfillment)

2. **Metrics**
   - Detection rate of planted logic flaws
   - False-positive rate on clean paths
   - Coverage of state-machine edges exercised by generated tests
   - Runtime and token (Ollama) cost per repository size

3. **Report artifact**
   - Markdown / PDF evaluation report under `plan/eval/` or `docs/eval/`.
   - Include concrete examples of findings with source-symbol linkage.

## Acceptance Criteria

- [ ] At least the planted BOLA and workflow-bypass flaws are detected.
- [ ] False-positive rate is documented and judged acceptable for the prototype.
- [ ] Evaluation report is reproducible from the committed fixtures and scripts.

## Deliverables

- Evaluation scripts + report
- Metrics tables
- PR `feat/eval-dvwa`
