import re
from typing import Dict, List

_PY_PARAM_LINE_RE = re.compile(
    r"^\s+(\w+)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$"
)

def _parse_python_docstring(docstring: str) -> Dict[str, List[str]]:
    """Split a Python docstring into named sections using a simple state machine."""
    sections: Dict[str, List[str]] = {"_main": []}
    current_section = "_main"
    lines = docstring.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Check if line looks like a header (e.g., "Args:", "Returns:")
        if stripped.endswith(":") and " " not in stripped:
            current_section = stripped[:-1].lower()
            sections[current_section] = []
        else:
            sections[current_section].append(line)

    return sections

def extract_params(docstring: str) -> List[Dict[str, str]]:
    sections = _parse_python_docstring(docstring)
    lines = sections.get("args") or sections.get("arguments") or sections.get("parameters") or []
    params: List[Dict[str, str]] = []

    for line in lines:
        m = _PY_PARAM_LINE_RE.match(line)
        if m:
            params.append({
                "name": m.group(1),
                "type": m.group(2) or "",
                "description": m.group(3).strip()
            })
    return params

def extract_returns(docstring: str) -> Dict[str, str]:
    sections = _parse_python_docstring(docstring)
    lines = sections.get("returns") or sections.get("return") or []
    if not lines:
        return {"type": "", "description": ""}
    
    # First line might be "type: description" or just "type"
    first = lines[0].strip()
    if ":" in first:
        parts = first.split(":", 1)
        return {"type": parts[0].strip(), "description": parts[1].strip() + " " + " ".join(l.strip() for l in lines[1:])}
    
    # Otherwise check if first line is just a type
    words = first.split()
    if len(words) == 1:
        return {"type": words[0], "description": " ".join(l.strip() for l in lines[1:])}
    
    cleaned_lines = [l.strip() for l in lines if l.strip()]
    return {"type": "", "description": " ".join(cleaned_lines)}

def extract_business_rules(docstring: str) -> List[str]:
    sections = _parse_python_docstring(docstring)
    rules: List[str] = []
    # Main description often contains rules
    main = sections.get("_main", [])
    for line in main:
        stripped = line.strip()
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only"]):
            rules.append(stripped)
    return rules
