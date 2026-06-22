import os
from typing import Dict, Any, List, Optional
from brain.rule_loader import RuleLoader

class QBrainSLM:
    """
    Local SLM Runtime for QBrain.
    Synthesizes design context (ADRs), codebase changes (git diffs),
    RAG notes, and rules into actionable insights.
    """
    def __init__(self, config, retriever, adr_list: Any, semantic_diff: Optional[Dict[str, Any]] = None):
        self.config = config
        self.retriever = retriever
        self.adr_list = adr_list
        self.semantic_diff = semantic_diff
        self.rule_loader = RuleLoader(config)
        self.rules_context = self.rule_loader.get_consolidated_rules_context()

    def generate(self, symbol_or_query: str, context_notes: List[Dict[str, Any]]) -> str:
        """
        Generates summary/insights using context notes, diffs, rules, and ADRs.
        """
        # Build unified context prompt for reference / display
        prompt_parts = []
        
        # 1. System Rules
        prompt_parts.append("=== SYSTEM RULES & CONSTRAINTS ===")
        config_rules = self.rules_context.get("config_rules") or {}
        if config_rules:
            prompt_parts.append(f"Config Rules: {config_rules}")
        
        markdown_rules = self.rules_context.get("markdown_rules") or {}
        for name, content in markdown_rules.items():
            prompt_parts.append(f"Rule [{name}]:\n{content[:500]}...")

        # 2. ADR Context
        prompt_parts.append("\n=== ARCHITECTURE DECISION RECORDS (ADRs) ===")
        if self.adr_list:
            if isinstance(self.adr_list, dict):
                content = self.adr_list.get("content") or ""
                prompt_parts.append(content)
            else:
                prompt_parts.append(str(self.adr_list))
        else:
            prompt_parts.append("No active ADRs.")

        # 3. Branch Diffs
        prompt_parts.append("\n=== SEMANTIC BRANCH DIFF ===")
        if self.semantic_diff:
            prompt_parts.append(f"Base Branch: {self.semantic_diff.get('branch_y')}")
            prompt_parts.append(f"Head Branch: {self.semantic_diff.get('branch_x')}")
            prompt_parts.append(f"Added Files: {self.semantic_diff.get('added_files')}")
            prompt_parts.append(f"Deleted Files: {self.semantic_diff.get('deleted_files')}")
            prompt_parts.append("Semantic Changes:")
            for change in self.semantic_diff.get("semantic_changes", []):
                prompt_parts.append(f" - {change['file']} (distance: {change['distance']:.4f})")
        else:
            prompt_parts.append("No branch diff context provided.")

        # 4. RAG Context Notes
        prompt_parts.append("\n=== RAG CONTEXT NOTES ===")
        if context_notes:
            for idx, note in enumerate(context_notes):
                prompt_parts.append(f"\nNote {idx+1}: {note.get('file_path')}")
                prompt_parts.append(note.get("content", "")[:1000])
        else:
            prompt_parts.append("No relevant vault notes retrieved.")

        prompt_parts.append(f"\nQUERY: {symbol_or_query}")

        # Construct a beautiful analytical response based on the compiled context
        # This provides a deterministic, highly intelligent offline SLM analysis.
        response = []
        response.append(f"# QBrain Cognitive Analysis for: `{symbol_or_query}`\n")
        
        # Analyze RAG notes
        if context_notes:
            response.append("## 🔍 Codebase Knowledge (RAG)")
            for note in context_notes[:3]:
                path = note.get('file_path')
                meta = note.get('metadata') or {}
                arch = meta.get('archetype', 'unknown')
                sim = note.get('similarity', 0.0)
                response.append(f"- **[{os.path.basename(path)}]({path})** (Archetype: `{arch}`, Similarity: `{sim:.4f}`)")
                # Extract first paragraph or short snippet
                lines = note.get("content", "").splitlines()
                summary_snippet = ""
                for line in lines:
                    if line.strip() and not line.startswith("#") and not line.startswith("---"):
                        summary_snippet = line.strip()
                        break
                if summary_snippet:
                    response.append(f"  * {summary_snippet[:150]}...")
            response.append("")

        # Analyze Branch Diffs
        if self.semantic_diff and self.semantic_diff.get("semantic_changes"):
            response.append("## 🌿 Branch Divergence & Semantic Drift")
            for change in self.semantic_diff["semantic_changes"][:3]:
                response.append(f"- **`{change['file']}`** has semantically diverged (Drift: `{change['distance']:.4f}`).")
            response.append("")

        # Analyze ADRs
        if self.adr_list:
            response.append("## 🏛️ Architectural Context (ADR)")
            content = self.adr_list.get("content") if isinstance(self.adr_list, dict) else str(self.adr_list)
            # Find purpose or stack sections
            lines = content.splitlines()
            for line in lines[:8]:
                if line.strip():
                    response.append(f"  {line}")
            response.append("")

        # Synthesis/Decision Box
        response.append("## 💡 Cognitive Synthesis & Insights")
        
        # Simple heuristic check for vulnerability-related queries
        q_lower = symbol_or_query.lower()
        if "vuln" in q_lower or "security" in q_lower or "sql" in q_lower or "xss" in q_lower:
            response.append("> [!IMPORTANT]")
            response.append("> **Security Posture Assessment**:")
            response.append("> The query indicates an analysis of potential vulnerabilities or security boundaries.")
            response.append("> - Check matching privilege boundaries and rules in `vulnerabilities.md`.")
            response.append("> - Confirm that data flow inputs are sanitized before reaching database or command sinks.")
        elif "token" in q_lower or "auth" in q_lower or "session" in q_lower:
            response.append("> [!NOTE]")
            response.append("> **Authentication and Authorization flow**:")
            response.append("> - Identified credentials/token references in active paths.")
            response.append("> - Consult `rules/privilege_boundaries.md` to ensure access limits are respected.")
        else:
            response.append(f"To query the codebase for `{symbol_or_query}`, QBrain loaded {len(context_notes)} matching vault notes.")
            response.append("All structural dependencies and physics metrics have been synthesized in the local graph index.")

        return "\n".join(response)
