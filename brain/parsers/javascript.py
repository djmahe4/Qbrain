import re
from typing import Dict, List

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
