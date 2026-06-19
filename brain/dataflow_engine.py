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

    def analyze_snippet(self, code: str, language: str, registry: Any = None, file_path: str = "unknown", redirectors: List[str] = None) -> Dict[str, Any]:
        """
        Builds a rich dataflow and structural model from a code snippet.
        """
        if not code:
            return {"variable_states": {}, "flow_paths": [], "synthesized_calls": [], "raw_atoms": []}
            
        lang = language.lower()
        var_states = {} # var_name -> {state, type, source, properties: {}, constraints: []}
        paths = [] # List of {source, sink, variable, state, file_path, line}
        synthesized_calls = []

        # Initialize var_states with registry constants if applicable
        if registry and lang == "php":
            for const_name, value in registry.constants.items():
                var_states[const_name] = {
                    "state": "CONSTANT",
                    "type": self._infer_type(str(value)),
                    "source": "internal",
                    "value": value,
                    "constraints": [],
                    "choices": [{"value": str(value), "constraints": [], "state": "CONSTANT"}]
                }

        # 1. Use Language-Specific Parser to extract raw dataflow atoms
        raw_atoms = []
        if lang == "php":
            raw_atoms = php.extract_dataflow(code, redirectors=redirectors)

        
        # 2. Process Atoms
        constraint_stack = [] # List of strings
        last_cond = None
        active_switch_cond = None
        
        for atom in raw_atoms:
            a_type = atom.get("type")
            line = atom.get("line")
            
            if a_type == "condition":
                verb = atom.get("verb")
                is_loop = verb in ("for", "foreach", "while")
                cond_content = atom.get("content", "")
                if len(cond_content) > 200: cond_content = cond_content[:197] + "..."
                
                if verb == "switch":
                    active_switch_cond = cond_content
                    last_cond = cond_content
                elif verb == "case" and active_switch_cond:
                    # Sibling isolation: clear previous case from stack
                    if constraint_stack and (constraint_stack[-1].startswith(f"{active_switch_cond} == ") or constraint_stack[-1] == active_switch_cond):
                        constraint_stack.pop()
                    
                    last_cond = f"{active_switch_cond} == {cond_content}"
                    # Immediately push if no brace expected (standard switch)
                    constraint_stack.append(last_cond)
                    last_cond = None
                elif verb == "default" and active_switch_cond:
                    if constraint_stack and (constraint_stack[-1].startswith(f"{active_switch_cond} == ") or constraint_stack[-1] == active_switch_cond):
                        constraint_stack.pop()
                    
                    last_cond = f"{active_switch_cond} == 'default'"
                    constraint_stack.append(last_cond)
                    last_cond = None
                elif not is_loop:
                    last_cond = cond_content
                
                if not last_cond and verb == "else": last_cond = "else branch"
                
                # Contextual sinks support: if the condition contains a non-constant variable
                if cond_content and not is_loop:
                    for var_name, data in var_states.items():
                        escaped_var = re.escape(var_name)
                        pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                        if re.search(pattern, cond_content):
                            # Check if the condition looks like a sink itself (e.g. contains mysqli_query)
                            # to avoid double-reporting it as both a condition and a sink
                            is_redundant = any(s in cond_content.lower() for s in ["query", "exec", "eval", "include", "require"])
                            if data.get("state") != "CONSTANT" and not is_redundant:
                                paths.append({
                                    "source": data.get("source", "unknown"),
                                    "sink": f"{verb} ({cond_content})",
                                    "variable": var_name,
                                    "state": data.get("state", "unknown"),
                                    "type": data.get("type", "unknown"),
                                    "file_path": file_path,
                                    "line": line,
                                    "constraints": list(constraint_stack)
                                })
            elif a_type == "scenario_switch":
                var_name = atom["variable"]
                value = atom["value"]
                constraint_stack.append(f"{var_name} == '{value}'")

            
            elif a_type == "delimiter" or a_type == "interrupt":
                val = atom.get("value")
                if val == "{":
                    if last_cond:
                        constraint_stack.append(last_cond)
                        last_cond = None
                elif val == "}":
                    if constraint_stack: 
                        popped = constraint_stack.pop()
                        if popped == active_switch_cond or (active_switch_cond and popped.startswith(f"{active_switch_cond} == ")):
                            if popped.startswith(f"{active_switch_cond} == ") and constraint_stack and constraint_stack[-1] == active_switch_cond:
                                constraint_stack.pop()
                            active_switch_cond = None
                elif val in ("break", "return"):
                    # Interrupt clears the current branch constraints for choices following it
                    last_cond = None

            curr_active_constraints = list(set(constraint_stack))
            if last_cond: curr_active_constraints.append(last_cond)

            if a_type == "usage":
                var = atom["variable"]
                if var not in var_states:
                    var_states[var] = {
                        "state": "DYNAMIC",
                        "type": "unknown",
                        "source": "internal",
                        "constraints": curr_active_constraints,
                        "choices": []
                    }

            if a_type == "global_state":
                var = atom["variable"]
                var_states[var] = {
                    "state": "GLOBAL_STATE",
                    "type": "dynamic",
                    "source": atom["source"],
                    "constraints": curr_active_constraints,
                    "choices": [{"value": atom["source"], "constraints": curr_active_constraints, "state": "GLOBAL_STATE"}]
                }
            elif a_type == "symbol_definition":
                s_kind = atom.get("kind")
                s_name = atom.get("variable")
                s_props = atom.get("properties", {})
                s_methods = atom.get("methods", [])
                
                if s_name not in var_states:
                    var_states[s_name] = {
                        "state": "DEFINITION",
                        "type": s_kind,
                        "source": "internal",
                        "properties": {},
                        "methods": s_methods,
                        "constraints": curr_active_constraints,
                        "choices": []
                    }
                
                for p_name, p_info in s_props.items():
                    var_states[s_name]["properties"][p_name] = {
                        "type": p_info.get("type", "unknown"),
                        "visibility": p_info.get("visibility"),
                        "default": p_info.get("default"),
                        "state": "MEMBER"
                    }

            elif a_type == "call":
                # Standard call handling - redirects now handled by synthesized_call atoms
                pass

            
            elif a_type == "constant":
                var = atom["variable"]
                var_states[var] = {
                    "state": "CONSTANT",
                    "type": self._infer_type(str(atom["value"])),
                    "source": "internal",
                    "value": atom["value"],
                    "constraints": curr_active_constraints,
                    "choices": [{"value": str(atom["value"]), "constraints": curr_active_constraints, "state": "CONSTANT"}]
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
                        "constraints": curr_active_constraints,
                        "choices": []
                    }
                elif "properties" not in var_states[base_var]:
                    var_states[base_var]["properties"] = {}

                inferred_type = self._infer_type(val_raw)
                if base_var == var_raw:
                    var_states[base_var]["type"] = inferred_type
                else:
                    var_states[base_var]["properties"][prop_name] = {"type": inferred_type, "value_hint": val_raw[:50]}
                    if var_states[base_var]["type"] == "unknown":
                        var_states[base_var]["type"] = "array" if "[" in var_raw else "object"

                state = var_states[base_var]["state"]
                source = var_states[base_var]["source"]
                is_tainted = any(s in val_raw or s in val_raw.lower() for s in ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_SERVER", "external_input"])
                is_sanitized = any(re.search(san, val_raw, re.IGNORECASE) for san in self.SANITIZERS.get(lang, []))
                
                if is_tainted:
                    state = "TAINTED"
                    source = next((s for s in ["$_GET", "$_POST", "$_REQUEST", "$_COOKIE", "$_SERVER", "external_input"] if s in val_raw or s in val_raw.lower()), "external")
                
                # Initialize state/source if not already tainted/safe
                # Initialize state/source if not already tainted/safe
                if "external_input" in val_raw:
                    state = "TAINTED"
                    source = "external"
                elif state == "CONSTANT": 
                    # Keep CONSTANT if the assigned value is a literal constant expression
                    # i.e., type is string/number/boolean and doesn't contain other variables
                    is_const_literal = inferred_type in ("string", "number", "boolean") and not any(
                        v in val_raw for v in var_states if v.startswith("$")
                    )
                    if not is_const_literal:
                        state = "DYNAMIC" 
                        source = "internal"
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
                
                var_states[base_var]["state"] = state
                var_states[base_var]["source"] = source

                # Track choices for scenario fan-out
                new_choice = {
                    "value": val_raw,
                    "constraints": curr_active_constraints,
                    "state": state,
                    "source": source
                }
                if "choices" not in var_states[base_var]:
                    var_states[base_var]["choices"] = []
                if new_choice not in var_states[base_var]["choices"]:
                    var_states[base_var]["choices"].append(new_choice)
                
                # Keep a single value_hint for backward compatibility
                if base_var == var_raw:
                    var_states[base_var]["value_hint"] = val_raw[:100]

            elif a_type == "synthesized_call":
                raw_path = atom["raw_path"]
                scenarios = [{"resolved": raw_path, "constraints": []}]
                
                for var, data in var_states.items():
                    if not var.startswith("$"): continue
                    escaped_var = re.escape(var)
                    pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                    
                    new_scenarios = []
                    for s in scenarios:
                        if not re.search(pattern, s["resolved"]):
                            new_scenarios.append(s)
                            continue
                            
                        choices = data.get("choices", [])
                        if not choices:
                            val_hint = data.get("value_hint", data.get("value", "..."))
                            new_resolved = re.sub(pattern, str(val_hint), s["resolved"])
                            new_scenarios.append({"resolved": new_resolved, "constraints": s["constraints"]})
                        else:
                            for choice in choices:
                                val = choice["value"]
                                if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                                    val = val[1:-1]
                                new_resolved = re.sub(pattern, str(val), s["resolved"])
                                new_constraints = list(set(s["constraints"] + choice.get("constraints", [])))
                                new_scenarios.append({"resolved": new_resolved, "constraints": new_constraints})
                    scenarios = new_scenarios

                if registry and lang == "php":
                    for const_name in registry.constants:
                        escaped_const = re.escape(const_name)
                        pattern = fr"(?<![\w\$]){escaped_const}(?![\w\$])"
                        val = registry.get_constant(const_name)
                        for s in scenarios:
                            if re.search(pattern, s["resolved"]):
                                s["resolved"] = re.sub(pattern, str(val), s["resolved"])
                
                for s in scenarios:
                    resolved_hint = s["resolved"]
                    for var, data in var_states.items():
                        if var.startswith("$"): continue
                        escaped_var = re.escape(var)
                        pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                        if re.search(pattern, resolved_hint):
                            val = data.get("value", "...")
                            resolved_hint = re.sub(pattern, str(val), resolved_hint)

                    resolved_hint = re.sub(r"['\"]\s*\.\s*", "", resolved_hint)
                    resolved_hint = re.sub(r"\s*\.\s*['\"]", "", resolved_hint)
                    resolved_hint = re.sub(r"(?<!\w)\.|\.(?!\w)", "/", resolved_hint)
                    resolved_hint = resolved_hint.replace("'", "").replace('"', "").replace("//", "/")
                    resolved_hint = resolved_hint.strip()
                    
                    synthesized_calls.append({
                        "verb": atom["verb"],
                        "raw": raw_path,
                        "resolved": resolved_hint,
                        "resolved_hint": resolved_hint,
                        "line": line,
                        "scenario_constraints": s["constraints"]
                    })
            elif a_type == "sink":
                sink_name = atom["sink"]
                args = atom["args"]
                
                for var_name, data in var_states.items():
                    escaped_var = re.escape(var_name)
                    pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                    if re.search(pattern, args):
                        if data.get("state") != "CONSTANT":
                            path = {
                                "source": data.get("source", "unknown"),
                                "sink": sink_name,
                                "variable": var_name,
                                "state": data.get("state", "unknown"),
                                "type": data.get("type", "unknown"),
                                "file_path": file_path,
                                "line": line,
                                "constraints": [c for choice in data.get("choices", []) for c in choice.get("constraints", [])]
                            }
                            if path not in paths:
                                paths.append(path)
            
            # Clear single-statement condition (no braces) after the first statement in its body
            if last_cond and a_type in ("assignment", "sink", "call", "usage"):
                last_cond = None
        return {
            "variable_states": var_states,
            "flow_paths": [{**dict(t), "constraints": list(dict(t).get("constraints", []))} for t in {tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in d.items())) for d in paths}],
            "synthesized_calls": synthesized_calls,
            "raw_atoms": raw_atoms
        }