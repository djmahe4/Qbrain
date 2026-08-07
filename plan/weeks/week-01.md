# Week 1 — Foundation: Agent Substrate & Skill Registry

**Phase:** 1 (Foundation)  
**PR Checkpoint:** `feat/agent-foundation`

## Goals

- Harden MCP integration and introduce the shared agent memory substrate.
- Bootstrap local Ollama and a minimal skill-loader so later weeks can register language/infra skills.
- Extend configuration surface without breaking existing CLI commands.

## Detailed Tasks

1. **Shared SQLite substrate**
   - Create / extend `qmd.sqlite` (or reuse `qbrain-mind-*.sqlite`) with table:
     ```sql
     CREATE TABLE IF NOT EXISTS agent_facts (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       symbol TEXT,
       hash TEXT UNIQUE,
       agent TEXT,
       payload TEXT,
       created_at REAL
     );
     ```
   - Add helper in `brain/persistence_manager.py` or a new `brain/agents/shared_memory.py`.

2. **Config extensions** (`brain/config.py`)
   - `ollama_base_url` (default `http://127.0.0.1:11434`)
   - `ollama_model` (default `qwen2.5-coder:7b`)
   - `agent_memory_path`
   - `skills_dir` (default `.qbrain/skills` or `skills/`)

3. **Skill loader skeleton**
   - `brain/agents/skill_loader.py` — discovers `SKILL.md` packages, parses front-matter, returns callables / knowledge dicts.
   - Follow skill-creator conventions (name, description, body).

4. **Ollama health check**
   - Lightweight CLI helper or `qbrain status` extension that verifies Ollama is reachable and lists available models.

5. **Documentation**
   - Update `README.md` architecture diagram to show agent substrate.
   - Add this plan directory under `plan/` (or `docs/plan/`) in the repo.

## Acceptance Criteria

- [ ] `agent_facts` table can be written and read by a unit test.
- [ ] Config loads the new keys with sensible defaults.
- [ ] Skill loader discovers at least one dummy skill package without error.
- [ ] Existing `qbrain index / audit / library sync` still pass the test suite.
- [ ] No external network calls (air-gap preserved).

## Deliverables

- `brain/agents/__init__.py`
- `brain/agents/shared_memory.py`
- `brain/agents/skill_loader.py`
- Config + persistence changes
- Unit tests under `tests/agents/`
- PR `feat/agent-foundation`
