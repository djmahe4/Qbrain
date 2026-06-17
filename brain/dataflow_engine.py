import re
from typing import List, Dict, Any, Set
from brain.parsers import php

class DataFlowEngine:
    """
    Analyzes code snippets to track variable lifecycles, rich states, types, and constraints.
    Acts as a coordinator using language-specific parsers.
    """
    
    # Generic patterns for fallback or common structures
    SOURCES = {
        "python": [r"request\.args", r"request\.form", r"request\.json", r"request\.values", r"input\("],
        "javascript": [r"req\.query", r"req\.body", r"req\.params", r"window\.location", r"localStorage"]
    }
    
    SANITIZERS = {
        "php": [r"htmlspecialchars", r"htmlentities", r"mysqli_real_escape_string", r"strip_tags", r"filter_var", r"intval", r"floatval"],
        "python": [r"escape\(", r"bleach\.clean", r"markupsafe\.escape"],
        "javascript": [r"validator\.escape", r"dompurify\.sanitize"]
    }
    
    SINKS = {
        "python": [r"print\(", r"execute\(", r"os\.system\(", r"subprocess\.", r"\w+\s*\("],
        "javascript": [r"console\.log\(", r"innerHTML\s*=", r"document\.write\(", r"eval\(", r"\w+\s*\("]
    }

    def _infer_type(self, value: str) -> str:
        """Heuristically infer type from value string."""
        v = value.strip()
        if not v: return "unknown"
        if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
            return "string"
        if v.startswith("[") or v.startswith("array(") or v.endswith("]"):
            return "array"
        if v.startswith("new "):
            return "object"
        if v.lower() in ("true", "false"):
            return "boolean"
        if v.replace(".", "", 1).isdigit():
            return "number"
        return "dynamic"

    def analyze_snippet(self, code: str, language: str) -> Dict[str, Any]:
        """
        Builds a rich dataflow and structural model from a code snippet.
        """
        if not code:
            return {"variable_states": {}, "flow_paths": [], "synthesized_calls": [], "raw_atoms": []}
            
        lang = language.lower()
        var_states = {} # var_name -> {state, type, source, properties: {}, constraints: []}
        paths = [] # List of {source, sink, variable, state}
        synthesized_calls = []
        
        # 1. Use Language-Specific Parser to extract raw dataflow atoms
        raw_atoms = []
        if lang == "php":
            raw_atoms = php.extract_dataflow(code)
        
        # 3. Process Atoms
        active_constraints = []
        constraint_stack = []
        last_cond = None
        
        for atom in raw_atoms:
            a_type = atom.get("type")
            
            if a_type == "condition":
                is_loop = atom.get("verb") in ("for", "foreach")
                cond_content = atom["content"]
                if len(cond_content) > 200: cond_content = cond_content[:197] + "..."
                if not is_loop: last_cond = cond_content
                if not last_cond and atom["verb"] == "else": last_cond = "else branch"
            
            elif a_type == "delimiter":
                if atom["value"] == "{":
                    if last_cond:
                        constraint_stack.append(last_cond)
                        last_cond = None
                elif atom["value"] == "}":
                    if constraint_stack: constraint_stack.pop()
            
            active_constraints = list(set(constraint_stack))
            if last_cond: active_constraints.append(last_cond)

            if a_type in ("global_state", "source"):
                var = atom["variable"]
                source_name = atom.get("source") or (var.split("[")[0] if "[" in var else "external")
                var_states[var] = {"state": "TAINTED", "type": "dynamic", "source": source_name, "constraints": list(active_constraints)}
            elif a_type == "assignment":
                var_raw, val_raw = atom["variable"], atom["value"]
                base_var = var_raw
                prop_name = None
                if "->" in var_raw:
                    parts = var_raw.split("->", 1)
                    base_var, prop_name = parts[0], parts[1]
                elif "[" in var_raw:
                    parts = var_raw.split("[", 1)
                    base_var, prop_name = parts[0], parts[1].strip("]'\" ")

                if base_var not in var_states:
                    var_states[base_var] = {"state": "CONSTANT", "type": "unknown", "source": "internal", "properties": {}, "constraints": list(active_constraints)}

                inferred_type = self._infer_type(val_raw)
                if base_var == var_raw: var_states[base_var]["type"] = inferred_type
                else:
                    var_states[base_var]["properties"][prop_name] = {"type": inferred_type, "value_hint": val_raw[:50]}
                    if var_states[base_var]["type"] == "unknown": var_states[base_var]["type"] = "array" if "[" in var_raw else "object"

                # Security Logic
                state, source = var_states[base_var]["state"], var_states[base_var]["source"]
                is_tainted = any(s in val_raw for s in ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_SERVER"])
                is_sanitized = any(re.search(san, val_raw, re.IGNORECASE) for san in self.SANITIZERS.get(lang, []))
                
                if is_tainted:
                    state = "TAINTED"
                    source = next((s for s in ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_SERVER"] if s in val_raw), "external")
                if is_sanitized: state = "SAFE"
                    
                # Inheritance
                for ex_var, ex_data in var_states.items():
                    if ex_var == base_var: continue
                    if re.search(fr"(?<![\w\$]){re.escape(ex_var)}(?![\w\$])", val_raw):
                        if ex_data["state"] == "TAINTED" and state != "SAFE":
                            state, source = "TAINTED", ex_data["source"]
                        elif ex_data["state"] == "SAFE":
                            state = "SAFE"
                            if ex_data["source"] != "internal": source = ex_data["source"]
                
                var_states[base_var]["state"], var_states[base_var]["source"] = state, source

            elif a_type == "synthesized_call":
                raw_path, resolved_hint = atom["raw_path"], atom["raw_path"]
                for var, data in var_states.items():
                    if var in raw_path: resolved_hint = resolved_hint.replace(var, f"{{{var}}}")
                synthesized_calls.append({"verb": atom["verb"], "raw_path": raw_path, "resolved_hint": resolved_hint, "constraints": list(active_constraints)})

            elif a_type == "sink":
                sink_name, args = atom["sink"], atom["args"]
                # Track constants (like defines) as part of dataflow state mapping
                if sink_name == "define":
                    parts = args.split(",", 1)
                    if len(parts) == 2:
                        c_name = parts[0].strip().strip("'\"")
                        c_val = parts[1].strip()
                        var_states[c_name] = {"state": "CONSTANT", "type": self._infer_type(c_val), "source": "internal", "constraints": list(active_constraints)}
                for var_name, data in var_states.items():
                    if re.search(fr"(?<![\w\$]){re.escape(var_name)}(?![\w\$])", args):
                        # Always track flows to sinks to provide richer dataflow descriptions
                        paths.append({"source": data.get("source", "internal"), "sink": sink_name, "variable": var_name, "state": data.get("state", "CONSTANT"), "type": data.get("type", "unknown"), "constraints": list(active_constraints)})

        return {
            "variable_states": var_states,
            "flow_paths": paths,
            "synthesized_calls": synthesized_calls,
            "raw_atoms": raw_atoms
        }
