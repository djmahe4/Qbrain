import re
from typing import List, Dict, Any, Set
from brain.parsers import php

class DataFlowEngine:
    """
    Analyzes code snippets to track variable lifecycles, rich states, types, and constraints.
    Enhanced to propagate line numbers and support scenario mapping.
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

    def analyze_snippet(self, code: str, language: str, registry: Any = None) -> Dict[str, Any]:
        """
        Builds a rich dataflow and structural model from a code snippet.
        """
        if not code:
            return {"variable_states": {}, "flow_paths": [], "synthesized_calls": [], "raw_atoms": []}
            
        lang = language.lower()
        var_states = {} # var_name -> {state, type, source, properties: {}, constraints: []}
        paths = [] # List of {source, sink, variable, state, line}
        synthesized_calls = []

        # Initialize var_states with registry constants if applicable
        if registry and lang == "php":
            for const_name, value in registry.constants.items():
                var_states[const_name] = {
                    "state": "CONSTANT",
                    "type": self._infer_type(str(value)),
                    "source": registry.get_origin(const_name) or "bootstrap",
                    "value": value,
                    "constraints": []
                }

        # 1. Use Language-Specific Parser to extract raw dataflow atoms
        raw_atoms = []
        if lang == "php":
            raw_atoms = php.extract_dataflow(code)
        
        # 2. Process Atoms
        constraint_stack = []
        last_cond = None
        
        for atom in raw_atoms:
            a_type = atom.get("type")
            line = atom.get("line")
            
            if a_type == "condition":
                is_loop = atom.get("verb") in ("for", "foreach")
                cond_content = atom.get("content", "")
                if len(cond_content) > 200: cond_content = cond_content[:197] + "..."
                if not is_loop: last_cond = cond_content
                if not last_cond and atom.get("verb") == "else": last_cond = "else branch"
            
            elif a_type == "delimiter":
                if atom.get("value") == "{":
                    if last_cond:
                        constraint_stack.append(last_cond)
                        last_cond = None
                elif atom.get("value") == "}":
                    if constraint_stack: constraint_stack.pop()
            
            curr_active_constraints = list(set(constraint_stack))
            if last_cond: curr_active_constraints.append(last_cond)

            if a_type == "global_state":
                var = atom["variable"]
                var_states[var] = {
                    "state": "GLOBAL_STATE",
                    "type": "dynamic",
                    "source": atom["source"],
                    "constraints": curr_active_constraints
                }
            
            elif a_type == "constant":
                var = atom["variable"]
                var_states[var] = {
                    "state": "CONSTANT",
                    "type": self._infer_type(str(atom["value"])),
                    "source": "internal",
                    "value": atom["value"],
                    "constraints": curr_active_constraints
                }
            
            elif a_type == "assignment":
                var_raw = atom["variable"]
                val_raw = atom["value"]
                base_var, prop_name = var_raw, None
                if "->" in var_raw:
                    parts = var_raw.split("->", 1)
                    base_var, prop_name = parts[0], parts[1]
                elif "[" in var_raw:
                    parts = var_raw.split("[", 1)
                    base_var, prop_name = parts[0], parts[1].strip("]'\" ")

                if base_var not in var_states:
                    var_states[base_var] = {
                        "state": "CONSTANT",
                        "type": "unknown",
                        "source": "internal",
                        "properties": {},
                        "constraints": curr_active_constraints
                    }

                inferred_type = self._infer_type(val_raw)
                if base_var == var_raw:
                    var_states[base_var]["type"] = inferred_type
                else:
                    var_states[base_var]["properties"][prop_name] = {"type": inferred_type, "value_hint": val_raw[:50]}
                    if var_states[base_var]["type"] == "unknown":
                        var_states[base_var]["type"] = "array" if "[" in var_raw else "object"

                state = var_states[base_var]["state"]
                source = var_states[base_var]["source"]
                is_tainted = any(s in val_raw for s in ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_SERVER"])
                is_sanitized = any(re.search(san, val_raw, re.IGNORECASE) for san in self.SANITIZERS.get(lang, []))
                
                if is_tainted:
                    state = "TAINTED"
                    source = next((s for s in ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_SERVER"] if s in val_raw), "external")
                if is_sanitized: state = "SAFE"
                    
                for existing_var, existing_data in var_states.items():
                    if existing_var == base_var: continue
                    escaped_var = re.escape(existing_var)
                    pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                    if re.search(pattern, val_raw):
                        if existing_data.get("state") == "TAINTED" and state != "SAFE":
                            state = "TAINTED"
                            source = existing_data.get("source", "external")
                        elif existing_data.get("state") == "SAFE":
                            state = "SAFE"
                            if existing_data.get("source") != "internal": source = existing_data.get("source")
                
                var_states[base_var]["state"] = state
                var_states[base_var]["source"] = source

            elif a_type == "synthesized_call":
                raw_path = atom["raw_path"]
                resolved_hint = raw_path
                
                # 1. Resolve against local variables
                for var, data in var_states.items():
                    if var.startswith("$"):
                        escaped_var = re.escape(var)
                        pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                        if re.search(pattern, resolved_hint):
                            val_hint = data.get("value_hint", data.get("value", "..."))
                            resolved_hint = re.sub(pattern, str(val_hint), resolved_hint)
                
                # 2. Resolve against registry constants
                if registry and lang == "php":
                    for const_name in registry.constants:
                        escaped_const = re.escape(const_name)
                        pattern = fr"(?<![\w\$]){escaped_const}(?![\w\$])"
                        if re.search(pattern, resolved_hint):
                            val = registry.get_constant(const_name)
                            resolved_hint = re.sub(pattern, str(val), resolved_hint)
                
                # Cleanup path separators and markers
                # Remove dots used for concatenation and handle quotes
                resolved_hint = re.sub(r"['\"]\s*\.\s*", "", resolved_hint) # 'a' . b -> ab
                resolved_hint = re.sub(r"\s*\.\s*['\"]", "", resolved_hint) # b . 'a' -> ab
                resolved_hint = re.sub(r"(?<!\w)\.|\.(?!\w)", "/", resolved_hint)
                resolved_hint = resolved_hint.replace("'", "").replace('"', "").replace("//", "/")
                resolved_hint = resolved_hint.strip()
                
                synthesized_calls.append({
                    "verb": atom["verb"],
                    "raw": raw_path,
                    "resolved": resolved_hint,
                    "line": line
                })

            elif a_type == "sink":
                sink_name = atom["sink"]
                args = atom["args"]
                for var_name, data in var_states.items():
                    escaped_var = re.escape(var_name)
                    pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                    if re.search(pattern, args):
                        if data.get("state") != "CONSTANT" or data.get("source") != "internal":
                            paths.append({
                                "source": data.get("source", "unknown"),
                                "sink": sink_name,
                                "variable": var_name,
                                "state": data.get("state", "unknown"),
                                "type": data.get("type", "unknown"),
                                "line": line
                            })

        return {
            "variable_states": var_states,
            "flow_paths": paths,
            "synthesized_calls": synthesized_calls,
            "raw_atoms": raw_atoms
        }
