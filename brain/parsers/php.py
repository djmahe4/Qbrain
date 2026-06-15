import re
from typing import Dict, List

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
        # Check if line looks like a tag (e.g., "@param", "@return")
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
    # Main description often contains rules
    main = sections.get("_main", [])
    for line in main:
        stripped = line.strip()
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only"]):
            rules.append(stripped)
    return rules

def extract_dataflow(code_snippet: str) -> List[Dict[str, str]]:
    """
    Identifies variable assignments and usages in a snippet.
    Very basic regex-based dataflow for now.
    """
    dataflow = []
    # Assignments: $var = ...; or $var .= ...;
    assign_pattern = re.compile(r"\$(\w+)\s*(\.|\+|-|\*|/)?=\s*([^;]+);")
    for match in assign_pattern.finditer(code_snippet):
        var_name = f"${match.group(1)}"
        op = match.group(2) or ""
        value = match.group(3).strip()
        dataflow.append({
            "variable": var_name,
            "operation": f"{op}=",
            "value": value
        })
    
    # Sinks: echo $var;, query($var), etc.
    sink_pattern = re.compile(r"\b(echo|print|query|die|header|setcookie)\b\s*\(?([^;)]+)\)?\s*;")
    for match in sink_pattern.finditer(code_snippet):
        sink_func = match.group(1)
        args = match.group(2).strip()
        dataflow.append({
            "sink": sink_func,
            "args": args
        })
        
    return dataflow
