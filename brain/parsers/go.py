import re
from typing import Dict, List

_GO_COMMENT_RE = re.compile(r"^//\s*(.+)$", re.MULTILINE)

# Match @param {type} name description
_JSDOC_STYLE = re.compile(r"@param\s+\{([^}]+)\}\s+(\w+)\s+(.*)", re.IGNORECASE)
# Match @param name type description
_GO_STYLE = re.compile(r"@param\s+(\w+)\s+(\w+)\s+(.*)", re.IGNORECASE)
# Match @param name description (no type)
_SIMPLE_STYLE = re.compile(r"@param\s+(\w+)\s+(.*)", re.IGNORECASE)

def extract_params(docstring: str) -> List[dict]:
    params: List[dict] = []
    # Clean up double slashes from lines
    lines = []
    for line in docstring.splitlines():
        line_clean = line.strip().lstrip("/").strip()
        if line_clean:
            lines.append(line_clean)
            
    for line in lines:
        # 1. JSDoc style
        m = _JSDOC_STYLE.search(line)
        if m:
            params.append({
                "name": m.group(2),
                "type": m.group(1),
                "description": m.group(3).strip()
            })
            continue
        # 2. Go style: @param name type description
        m = _GO_STYLE.search(line)
        if m:
            params.append({
                "name": m.group(1),
                "type": m.group(2),
                "description": m.group(3).strip()
            })
            continue
        # 3. Simple style: @param name description
        m = _SIMPLE_STYLE.search(line)
        if m:
            params.append({
                "name": m.group(1),
                "type": "",
                "description": m.group(2).strip()
            })
    return params

# Match @return type description
_GO_RETURN_STYLE = re.compile(r"@returns?\s+(\w+)\s+(.*)", re.IGNORECASE)
# Match @return {type} description
_JSDOC_RETURN_STYLE = re.compile(r"@returns?\s+\{([^}]+)\}\s+(.*)", re.IGNORECASE)
# Match @return description
_SIMPLE_RETURN_STYLE = re.compile(r"@returns?\s+(.*)", re.IGNORECASE)

def extract_returns(docstring: str) -> dict:
    lines = []
    for line in docstring.splitlines():
        line_clean = line.strip().lstrip("/").strip()
        if line_clean:
            lines.append(line_clean)
            
    for line in lines:
        m = _JSDOC_RETURN_STYLE.search(line)
        if m:
            return {"type": m.group(1), "description": m.group(2).strip()}
        m = _GO_RETURN_STYLE.search(line)
        if m:
            return {"type": m.group(1), "description": m.group(2).strip()}
        m = _SIMPLE_RETURN_STYLE.search(line)
        if m:
            return {"type": "", "description": m.group(1).strip()}
            
    return {"type": "", "description": ""}

def extract_business_rules(docstring: str) -> List[str]:
    """Extract meaningful lines from Go comment blocks (// ...)."""
    lines = _GO_COMMENT_RE.findall(docstring)
    # Simple heuristic: lines with more than 5 words or containing keywords
    return [l for l in lines if len(l) > 5]
