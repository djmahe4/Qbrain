import re
from typing import Dict, List, Any

_PHP_PARAM_RE = re.compile(
    r"@param\s+(?:\{([^}]*)\}\s+)?\$(\w+)\s+(.*)", re.IGNORECASE
)
_PHP_RETURNS_RE = re.compile(
    r"@returns?\s+(?:\{([^}]*)\}\s+)?(.*)", re.IGNORECASE
)

def _parse_php_docstring(docstring: str) -> Dict[str, List[str]]:
    """Split a PHP docstring into sections."""
    sections: Dict[str, List[str]] = {"_main": []}
    current_section = "_main"
    lines = docstring.splitlines()

    for line in lines:
        stripped = line.strip().lstrip("/* ").rstrip("*/ ")
        if not stripped:
            continue
        if stripped.startswith("@"):
            tag = stripped.split(" ", 1)[0][1:].lower()
            current_section = tag
            sections.setdefault(current_section, []).append(stripped)
        else:
            sections[current_section].append(stripped)

    return sections

def extract_params(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    for m in _PHP_PARAM_RE.finditer(docstring):
        params.append({
            "name": f"${m.group(2)}",
            "type": m.group(1) or "",
            "description": m.group(3).strip()
        })
    return params

def extract_returns(docstring: str) -> Dict[str, str]:
    m = _PHP_RETURNS_RE.search(docstring)
    if m:
        return {
            "type": m.group(1) or "",
            "description": m.group(2).strip()
        }
    return {"type": "", "description": ""}

def extract_business_rules(docstring: str) -> List[str]:
    rules: List[str] = []
    sections = _parse_php_docstring(docstring)
    main = sections.get("_main", [])
    for line in main:
        stripped = line.strip()
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only"]):
            rules.append(stripped)
    return rules

def extract_dataflow(code_snippet: str) -> List[Dict[str, Any]]:
    """
    Identifies variable assignments, usages, and synthesized dependencies in PHP.
    """
    dataflow = []
    
    # 1. Globals Detection
    for var_name in re.findall(r"\$_(SESSION|COOKIE|GET|POST|REQUEST|SERVER|FILES)\[['\"](\w+)['\"]\]", code_snippet):
        dataflow.append({
            "type": "global_state",
            "variable": f"$_{var_name[0]}['{var_name[1]}']",
            "source": f"$_{var_name[0]}"
        })

    # 2. Assignments
    # Supports $var, $obj->prop, $arr['key']
    assign_pattern = re.compile(r"(\$[\w\->\[\]'\" ]+)\s*([\.\+\-\*\/]?=)\s*([^;]+);")
    for match in assign_pattern.finditer(code_snippet):
        dataflow.append({
            "type": "assignment",
            "variable": match.group(1).strip(),
            "operation": match.group(2),
            "value": match.group(3).strip()
        })
    
    # 3. Dynamic Includes (Synthesized Dependencies)
    include_pattern = re.compile(r"\b(include|require)(_once)?\b\s*\(?([^;]+)\)?\s*;", re.IGNORECASE)
    for match in include_pattern.finditer(code_snippet):
        dataflow.append({
            "type": "synthesized_call",
            "verb": match.group(1),
            "raw_path": match.group(3).strip()
        })

    # 4. Sinks
    sink_pattern = re.compile(r"\b(echo|print|query|die|header|setcookie|mysqli_query|mysqli_prepare|eval|exec|system|shell_exec)\b\s*\(?([^;)]+)\)?\s*;")
    for match in sink_pattern.finditer(code_snippet):
        dataflow.append({
            "type": "sink",
            "sink": match.group(1),
            "args": match.group(2).strip()
        })
        
    return dataflow
