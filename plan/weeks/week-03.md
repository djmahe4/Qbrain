# Week 3 — Workflow Extraction: Language Subagent + PHP Skill

**Phase:** 2 (Workflow Extraction)  
**PR Checkpoint:** `feat/lang-subagent-php`

## Goals

- Introduce the **Language Subagent** that enriches Context Builder facts.
- Ship the highest-priority skill: `qbrain-lang-php` (DVWA + Laravel + plain PHP).
- Demonstrate multi-level enrichment (Level 0 → Level 1).

## Detailed Tasks

1. **`brain/agents/language_subagent.py`**
   - Consumes a Context-Builder fact.
   - Detects language (reuse `detect_language` + explicit field).
   - Calls existing `LanguageParser` / `brain/parsers/*` for base genome.
   - Loads the matching skill and invokes `extract_privilege_atoms`, `extract_framework_hints`, etc.
   - Writes enriched fact (with `parent_hash`) back to shared memory.

2. **Skill package `skills/qbrain-lang-php/SKILL.md`**
   - Front-matter + body encoding:
     - Superglobals & session/role patterns
     - Laravel Gate / Policy / middleware aliases
     - Symfony security voters (light)
     - DVWA security-level scenario switches
     - Common sinks relevant to business-logic (header Location, query, eval, …)
   - Skill exposes pure functions the subagent can call; no heavy LLM required at this stage.

3. **Wire into Context Builder**
   - After MCP expansion, automatically call Language Subagent when language is known.

4. **Tests**
   - PHP fixture (snippet of DVWA-like controller) → assert privilege atoms and framework hints appear.

## Acceptance Criteria

- [ ] Language Subagent produces enriched facts for PHP files.
- [ ] Skill is discovered by the skill loader.
- [ ] Privilege atoms contain at least session/role/auth-related variables for the fixture.
- [ ] Parent-hash linkage is preserved so DATG can reconstruct lineage.
- [ ] No regression in Context Builder or existing parsers.

## Deliverables

- `LanguageSubagent`
- `skills/qbrain-lang-php/`
- Integration with Context Builder
- Tests + PR `feat/lang-subagent-php`
