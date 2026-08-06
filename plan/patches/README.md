# Patches / Scaffolding Notes

This directory is reserved for unified `git diff` patches that implement the agent and skill scaffolding described in the weekly plans.

Because the primary deliverable of the current PR is the **plan itself**, concrete code patches will be attached to the per-week feature PRs:

| Checkpoint | Expected patch focus |
|------------|----------------------|
| `feat/agent-foundation` | shared_memory, skill_loader, config keys |
| `feat/context-builder` | `brain/agents/context_builder.py` + CLI |
| `feat/lang-subagent-php` | LanguageSubagent + `skills/qbrain-lang-php` |
| … | … |

When generating a patch for a follow-up PR, place the unified diff here (or attach it directly to the GitHub PR) and reference the corresponding `plan/weeks/week-XX.md` acceptance criteria.
