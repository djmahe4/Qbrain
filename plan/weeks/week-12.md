# Week 12 — Reporting: Final Release & Documentation

**Phase:** 6 (Reporting)  
**PR Checkpoint:** `release/v0.2.0`

## Goals

- Produce the final project report, release notes, and open-source package.
- Freeze the agent/skill architecture for the v0.2 line.

## Detailed Tasks

1. **Documentation**
   - Update root `README.md` with the multi-agent architecture diagram and quick-start for `qbrain agent-run`.
   - Add `docs/agents.md` describing each agent, the skill format, and the DATG hash formula.
   - Finalize this `plan/` directory as the living project plan.

2. **Release artifacts**
   - CHANGELOG entry for agent + skill machinery.
   - Tagged release `v0.2.0` (or appropriate version).
   - Optional evaluation PDF derived from Week 10 report.

3. **Cleanup**
   - Ensure all temporary generation scripts live under `/tmp` or are removed; only deliverables remain in the repo.
   - Verify air-gap claims (no external model calls by default).

4. **Handover**
   - List known limitations and recommended next steps (more language skills, richer domain templates, CI integration).

## Acceptance Criteria

- [ ] A clean clone + `uv sync` + `qbrain agent-run` on the DVWA fixture produces findings without external network.
- [ ] Documentation is sufficient for a new contributor to add a language skill.
- [ ] Release tag and CHANGELOG are published.

## Deliverables

- Updated README / docs
- CHANGELOG + release tag
- Final evaluation / project report
- PR / release `v0.2.0`
