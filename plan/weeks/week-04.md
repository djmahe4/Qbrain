# Week 4 — Workflow Extraction: Remaining Language Skills + Infra Subagent

**Phase:** 2 (Workflow Extraction)  
**PR Checkpoint:** `feat/lang-infra-skills`

## Goals

- Complete the core language skill set (Python, JS/TS).
- Introduce the **Infra Subagent** for cross-service and deployment privilege edges.
- Close Phase 2 with multi-level enrichment fully operational.

## Detailed Tasks

1. **Skills**
   - `skills/qbrain-lang-python/SKILL.md`  
     FastAPI `Depends` / security schemes, Django `permission_classes` / `LoginRequiredMixin`, Flask login patterns.
   - `skills/qbrain-lang-js/SKILL.md`  
     Express middleware chains, NestJS Guards / Interceptors, Next.js API route auth.
   - Optional light skills for Go / Rust if time permits.

2. **`brain/agents/infra_subagent.py`**
   - Scans for:
     - `docker-compose*.yml` / `Dockerfile` (service boundaries, exposed ports)
     - Kubernetes manifests (RBAC, ServiceAccounts, NetworkPolicies)
     - OpenAPI / Swagger files (`securitySchemes`, `security`)
     - `.env*`, CI workflow secrets, Terraform (light heuristics)
   - Emits `CROSS_SERVICE` and privilege-boundary edges into `agent_facts`.

3. **Skill `skills/qbrain-infra/SKILL.md`**
   - Knowledge of common privilege leakage patterns (env vars containing secrets, overly permissive K8s roles, missing OpenAPI security on mutating operations).

4. **Orchestration**
   - Context Builder (or a thin coordinator) invokes Language Subagent then Infra Subagent in sequence for each expanded node / project.

## Acceptance Criteria

- [ ] Python and JS fixtures produce framework-specific privilege atoms.
- [ ] Infra Subagent detects at least one Docker Compose service boundary and one OpenAPI security scheme in a test fixture.
- [ ] All enriched facts remain queryable by symbol + language + agent type.
- [ ] Skill loader handles multiple concurrent skills without collision.

## Deliverables

- Additional language skills + Infra Subagent + skill
- End-to-end enrichment test for a mixed-language mini-repo
- PR `feat/lang-infra-skills`
