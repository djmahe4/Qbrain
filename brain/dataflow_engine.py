import re
from typing import List, Dict, Any, Set

class DataFlowEngine:
    """
    Analyzes code snippets to track variable lifecycles, states, and dataflow paths.
    """
    
    SOURCES = {
        "php": [r"\$_GET", r"\$_POST", r"\$_REQUEST", r"\$_COOKIE", r"\$_SESSION", r"\$_SERVER", r"\$_FILES"],
        "python": [r"request\.args", r"request\.form", r"request\.json", r"request\.values", r"input\("],
        "javascript": [r"req\.query", r"req\.body", r"req\.params", r"window\.location", r"localStorage"]
    }
    
    SANITIZERS = {
        "php": [r"htmlspecialchars", r"htmlentities", r"mysqli_real_escape_string", r"strip_tags", r"filter_var", r"intval", r"floatval"],
        "python": [r"escape\(", r"bleach\.clean", r"markupsafe\.escape"],
        "javascript": [r"validator\.escape", r"dompurify\.sanitize"]
    }
    
    SINKS = {
        "php": [r"echo\b", r"print\b", r"query\(", r"exec\(", r"system\(", r"shell_exec\(", r"header\(", r"setcookie\("],
        "python": [r"print\(", r"execute\(", r"os\.system\(", r"subprocess\."],
        "javascript": [r"console\.log\(", r"innerHTML\s*=", r"document\.write\(", r"eval\("]
    }

    def analyze_snippet(self, code: str, language: str) -> Dict[str, Any]:
        """
        Builds a dataflow model from a code snippet.
        """
        if not code:
            return {"variable_states": {}, "flow_paths": []}
            
        lang = language.lower()
        var_states = {} # var_name -> state (TAINTED, SAFE, CONSTANT)
        paths = [] # List of {source, sink, variable, state}
        
        # 1. Identify direct sources in snippet
        sources_found = []
        for src_pattern in self.SOURCES.get(lang, []):
            for match in re.finditer(src_pattern, code):
                sources_found.append(match.group(0))
        
        # 2. Track assignments and propagation
        lines = code.splitlines()
        for line in lines:
            # Assignment regex (supports common languages)
            assign_match = re.search(r"(\$[\w\->]+|let\s+\w+|const\s+\w+|var\s+\w+|\w+)\s*([\.\+\-\*\/]?=)\s*([^;]+)", line)
            if assign_match:
                var_raw = assign_match.group(1).replace("let ", "").replace("const ", "").replace("var ", "").strip()
                val_raw = assign_match.group(3).strip()
                
                state = "CONSTANT"
                
                # Check if value comes from source (case-insensitive)
                is_tainted = any(re.search(src, val_raw, re.IGNORECASE) for src in self.SOURCES.get(lang, []))
                # Check if value is sanitized (case-insensitive)
                is_sanitized = any(re.search(san, val_raw, re.IGNORECASE) for san in self.SANITIZERS.get(lang, []))
                
                if is_tainted:
                    state = "TAINTED"
                if is_sanitized:
                    state = "SAFE"
                    
                # Inherit state if assigning from another variable
                for existing_var, existing_state in var_states.items():
                    escaped_var = re.escape(existing_var)
                    # Custom boundary check for variables (especially those starting with $)
                    pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                    if re.search(pattern, val_raw):
                        if existing_state == "TAINTED" and state != "SAFE":
                            state = "TAINTED"
                        elif existing_state == "SAFE":
                            state = "SAFE"
                
                var_states[var_raw] = state
                
            # 3. Detect flows to sinks
            for sink_pattern in self.SINKS.get(lang, []):
                if re.search(sink_pattern, line, re.IGNORECASE):
                    # Find which variables are in this sink line
                    for var_name, state in var_states.items():
                        escaped_var = re.escape(var_name)
                        pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                        if re.search(pattern, line):
                            paths.append({
                                "source": sources_found[0] if sources_found else "internal",
                                "sink": sink_pattern.replace("\\b", "").replace("\\", "").replace("(", ""),
                                "variable": var_name,
                                "state": state
                            })
        
        return {
            "variable_states": var_states,
            "flow_paths": paths
        }
