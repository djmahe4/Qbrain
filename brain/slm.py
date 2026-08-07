import os
import re
from typing import Dict, Any, List, Optional
from brain.rule_loader import RuleLoader

def truncate_context_aware(text: str, max_chars: int = 500) -> str:
    if len(text) <= max_chars:
        return text
    sliced = text[:max_chars]
    # Try paragraph boundary first
    last_double = sliced.rfind("\n\n")
    if last_double > max_chars * 0.5:
        return text[:last_double] + "\n\n... [truncated for context limits]"
    # Try line boundary next
    last_single = sliced.rfind("\n")
    if last_single > max_chars * 0.5:
        return text[:last_single] + "\n... [truncated for context limits]"
    # Try word boundary
    last_space = sliced.rfind(" ")
    if last_space > max_chars * 0.5:
        return text[:last_space] + " ... [truncated for context limits]"
    return sliced + "..."

def _extract_multi_section(content: str) -> str:
    target_headers = {
        "## Semantic Context", 
        "## Entanglements", 
        "## Dynamic Variable Tracking", 
        "## Assumed Environmental Context"
    }
    extracted_blocks = []
    lines = content.splitlines()
    current_header = None
    current_block = []

    def flush_block():
        if current_header and any(current_header.startswith(th) for th in target_headers):
            if current_header.startswith("## Dynamic Variable Tracking"):
                # keep header + table header + first row
                table_lines = [l for l in current_block if l.strip().startswith("|")]
                if len(table_lines) >= 3:
                    extracted_blocks.append(current_header + "\n" + "\n".join(table_lines[:3]))
            else:
                extracted_blocks.append(current_header + "\n" + "\n".join(current_block[:4]))

    for line in lines:
        if line.startswith("## "):
            flush_block()
            current_header = line.strip()
            current_block = []
        elif current_header:
            if line.strip() and not line.strip().startswith("---"):
                current_block.append(line)
    flush_block()

    res = "\n\n".join(extracted_blocks)
    if not res:
        # Fallback to first non-empty line
        for line in lines:
            if line.strip() and not line.startswith("#") and not line.startswith("---"):
                return line.strip()
    return res

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

    def generate(self, symbol_or_query: str, context_notes: List[Dict[str, Any]], correlation_context: Optional[str] = None, code_snippet: Optional[str] = None) -> str:
        """
        Generates summary/insights using context notes, diffs, rules, and ADRs.
        """
        response = []
        response.append(f"# QBrain Cognitive Analysis for: `{symbol_or_query}`\n")
        
        # Analyze RAG notes
        if context_notes:
            response.append("## 🔍 Codebase Knowledge (RAG)")
            for note in context_notes[:3]:
                path = note.get('file_path', '')
                meta = note.get('metadata') or {}
                arch = meta.get('archetype', 'unknown')
                sim = note.get('similarity', 0.0)
                response.append(f"- **[{os.path.basename(path)}]({path})** (Archetype: `{arch}`, Similarity: `{sim:.4f}`)")
                
                extracted_text = _extract_multi_section(note.get("content", ""))
                truncated = truncate_context_aware(extracted_text, max_chars=400)
                if truncated:
                    for line in truncated.splitlines():
                        response.append(f"  > {line}")
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

        # Live Dataflow Analysis (Step 5)
        if code_snippet and self.config.data.get("language", "php").lower() == "php":
            try:
                from brain.dataflow_engine import DataFlowEngine
                df_res = DataFlowEngine().analyze_snippet(code_snippet, "php")
                response.append("## 🔬 Live Dataflow Analysis")
                var_states = df_res.get("variable_states", {})
                tainted = [v for v, data in var_states.items() if data.get("state") == "TAINTED"]
                flow_paths = df_res.get("flow_paths", [])
                
                if tainted:
                    response.append(f"- **Tainted Variables Found**: {', '.join(tainted)}")
                if flow_paths:
                    for p in flow_paths:
                        response.append(f"- **Flow Path**: {p.get('source')} → {p.get('variable')} → {p.get('sink')} (Length: {df_res.get('path_length', len(tainted))})")
                response.append("")
            except Exception as e:
                response.append(f"## 🔬 Live Dataflow Analysis\n- Error analyzing snippet: {str(e)}\n")

        # Analyze Quantum Correlations (Reformatted as Markdown Table)
        if correlation_context:
            response.append("## 🔀 Semantic Correlations")
            if "Static taint summary" in correlation_context:
                response.append(correlation_context)
            else:
                response.append("| Symbol | Comment Match | Score | Flip | Decoherence |")
                response.append("|---|---|---|---|---|")
                for line in correlation_context.splitlines():
                    # Format: - Comment in file.py:12 entangled with func_name (cosine: 0.85) [FLIP (...), DECOHERENCE]
                    match = re.search(r'- Comment in (.*?) entangled with (.*?) \(cosine: (.*?)\)(?: \[(.*?)\])?', line)
                    if match:
                        file_loc, symbol, score, statuses = match.groups()
                        statuses = statuses or ""
                        flip = "Yes" if "FLIP" in statuses else "No"
                        decoherence = "Yes" if "DECOHERENCE" in statuses else "No"
                        response.append(f"| `{symbol}` | `{file_loc}` | `{score}` | {flip} | {decoherence} |")
                    else:
                        response.append(line)
            response.append("")

        # Synthesis/Decision Box
        response.append("## 💡 Cognitive Synthesis & Insights")
        
        q_lower = symbol_or_query.lower()
        is_security = (
            any(k in q_lower for k in ["vuln", "security", "sql", "xss", "csrf", "upload", "bypass", "inject"]) or
            any("behavior" in note.get("file_path", "").lower() for note in context_notes) or
            any(note.get("metadata", {}).get("security_level") for note in context_notes) or
            any(note.get("metadata", {}).get("constraints") for note in context_notes)
        )
        if is_security:
            # Dynamically determine heading based on query/context
            has_explicit_security = (
                any(k in q_lower for k in ["vuln", "security", "sql", "xss", "csrf", "upload", "bypass", "inject"]) or
                any("vuln" in str(note.get("metadata", {})).lower() for note in context_notes)
            )
            heading = "Security Posture Assessment" if has_explicit_security else "Environmental & Constraint Assessment"
            
            response.append("> [!IMPORTANT]")
            response.append(f"> **{heading}**:")
            response.append("> The query or retrieved context indicates an analysis of potential vulnerabilities or environmental constraints.")
            
            for note in context_notes:
                meta = note.get('metadata') or {}
                # Behaviors -> sec level and taint
                sec_level = meta.get("security_level")
                constraints = meta.get("constraints") or {}
                dataflow = meta.get("dataflow_summary")
                # Symbols -> callers
                entanglements = meta.get("entanglement_count")
                
                evidence = []
                path = note.get('file_path', '')
                base_name = os.path.basename(path).replace(".md", "")
                
                if "behaviors" in path:
                    if constraints:
                        for var, val in constraints.items():
                            evidence.append(f"constraint `{var} == {val}`")
                    elif sec_level:
                        evidence.append(f"constraint `{sec_level}`")
                    if dataflow:
                        # try to extract source/sink or just the row
                        evidence.append(f"dataflow state `{dataflow.strip()}`")
                elif "symbols" in path and entanglements:
                    evidence.append(f"`{entanglements}` entangled callers")
                elif "files" in path:
                    content = note.get("content", "")
                    findings = []
                    in_sec_section = False
                    
                    # Extract findings from the 'Security Findings' or 'Security Findings' section
                    for line in content.splitlines():
                        line_stripped = line.strip()
                        if "security findings" in line_stripped.lower():
                            in_sec_section = True
                            continue
                        elif line_stripped.startswith("## ") and in_sec_section:
                            in_sec_section = False
                        
                        if in_sec_section and line_stripped.startswith("-"):
                            # Clean up markdown bullet and bold styling
                            clean_finding = re.sub(r'^-\s*(\*\*[^*]+\*\*:\s*)?', '', line_stripped)
                            if clean_finding:
                                findings.append(clean_finding)
                    
                    if findings:
                        # Append the dynamically extracted findings
                        evidence.extend(findings[:2])  # Limit to top 2 to keep context concise
                    else:
                        # Fallback to tainted variables list if no explicit findings section exists
                        tainted_vars = re.findall(r'\|\s*(\$[\w_]+)\s*\|\s*[^|]*?\s*\|\s*`?TAINTED`?\s*\|', content)
                        if tainted_vars:
                            vars_str = ", ".join(f"`{v}`" for v in tainted_vars)
                            evidence.append(f"tainted variables: {vars_str}")
                
                if evidence:
                    response.append(f"> - **{base_name}** — {', '.join(evidence)}.")
                    
        elif "token" in q_lower or "auth" in q_lower or "session" in q_lower:
            response.append("> [!NOTE]")
            response.append("> **Authentication and Authorization flow**:")
            response.append("> - Identified credentials/token references in active paths.")
            response.append("> - Consult `rules/privilege_boundaries.md` to ensure access limits are respected.")
        else:
            response.append(f"To query the codebase for `{symbol_or_query}`, QBrain loaded {len(context_notes)} matching vault notes.")
            response.append("All structural dependencies and physics metrics have been synthesized in the local graph index.")

        return "\n".join(response)
