import re
from typing import Dict, List, Any

_JSDOC_PARAM_RE = re.compile(
    r"@param\s+(?:\{([^}]*)\}\s+)?(\w+)\s+(.*)", re.IGNORECASE
)
_JSDOC_RETURNS_RE = re.compile(
    r"@returns?\s+(?:\{([^}]*)\}\s+)?(.*)", re.IGNORECASE
)

def extract_params(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    for m in _JSDOC_PARAM_RE.finditer(docstring):
        params.append({
            "name": m.group(2),
            "type": m.group(1) or "",
            "description": m.group(3).strip()
        })
    return params

def extract_returns(docstring: str) -> Dict[str, str]:
    m = _JSDOC_RETURNS_RE.search(docstring)
    if m:
        return {
            "type": m.group(1) or "",
            "description": m.group(2).strip()
        }
    return {"type": "", "description": ""}

def extract_business_rules(docstring: str) -> List[str]:
    # JSDoc often has @rule or just mentions in description
    rules: List[str] = []
    lines = docstring.splitlines()
    for line in lines:
        stripped = line.strip().lstrip("/* ").rstrip("*/ ")
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only"]):
            rules.append(stripped)
    return rules

def extract_dataflow(code_snippet: str) -> List[Dict[str, Any]]:
    """
    Identifies variable assignments, usages, and control flow in JS/TS.
    """
    dataflow = []
    lines = code_snippet.splitlines(keepends=True)
    line_starts = [0]
    for line in lines:
        line_starts.append(line_starts[-1] + len(line))
        
    def get_line(pos):
        import bisect
        return bisect.bisect_right(line_starts, pos)

    current_pos = 0
    for idx, line in enumerate(lines, 1):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("//") or line_stripped.startswith("/*"):
            current_pos += len(line)
            continue
            
        # 1. Parameter matching from function definition
        func_match = re.match(r"^function\s+\w+\s*\(([^)]*)\)", line_stripped)
        if func_match:
            params = func_match.group(1).split(",")
            for p in params:
                p_name = p.split(":")[0].strip()
                if p_name:
                    dataflow.append({
                        "type": "assignment",
                        "variable": p_name,
                        "operation": "=",
                        "value": "param_input",
                        "pos": current_pos + func_match.start(1),
                        "line": idx
                    })
                    
        # 2. Variable declarations (const/let/var x = ...)
        decl_match = re.match(r"^(?:const|let|var)\s+(\w+)\s*(=|\+=|-=)\s*(.+)$", line_stripped)
        if decl_match:
            dataflow.append({
                "type": "assignment",
                "variable": decl_match.group(1),
                "operation": decl_match.group(2),
                "value": decl_match.group(3).strip(),
                "pos": current_pos + decl_match.start(1),
                "line": idx
            })
            
        # 3. Standard assignments (x = val)
        elif not line_stripped.startswith("function "):
            assign_match = re.match(r"^(\w+)\s*(=|\+=|-=)\s*(.+)$", line_stripped)
            if assign_match:
                dataflow.append({
                    "type": "assignment",
                    "variable": assign_match.group(1),
                    "operation": assign_match.group(2),
                    "value": assign_match.group(3).strip(),
                    "pos": current_pos + assign_match.start(1),
                    "line": idx
                })
                
        # 4. Conditions
        cond_match = re.search(r"\b(if|while|for)\b\s*\((.+)\)", line_stripped)
        if cond_match:
            dataflow.append({
                "type": "condition",
                "verb": cond_match.group(1),
                "content": cond_match.group(2).strip(),
                "pos": current_pos + cond_match.start(2),
                "line": idx
            })
            
        # 5. Delimiters
        for char_idx, char in enumerate(line_stripped):
            if char in ("{", "}"):
                dataflow.append({
                    "type": "delimiter",
                    "value": char,
                    "pos": current_pos + char_idx,
                    "line": idx
                })
                
        # 6. Returns and Throws
        interrupt_match = re.match(r"^(return|throw)\b\s*(.*)$", line_stripped)
        if interrupt_match:
            dataflow.append({
                "type": "interrupt",
                "value": interrupt_match.group(1),
                "pos": current_pos,
                "line": idx
            })
            
        current_pos += len(line)

    dataflow.sort(key=lambda x: x.get("pos", 0))
    return dataflow

