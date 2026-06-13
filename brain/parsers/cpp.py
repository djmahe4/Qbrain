import re
from typing import Dict, List

_CPP_PARAM_RE = re.compile(r"(?:@|\\)param(?:\s*\[[^\]]*\])?\s+(\w+)\s+(.*)", re.IGNORECASE)
_CPP_RETURNS_RE = re.compile(r"(?:@|\\)returns?\s+(.*)", re.IGNORECASE)
_CPP_BRIEF_RE = re.compile(r"(?:@|\\)brief\s+(.*)", re.IGNORECASE)

def extract_params(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    for m in _CPP_PARAM_RE.finditer(docstring):
        params.append({
            "name": m.group(1),
            "type": "",
            "description": m.group(2).strip()
        })
    return params

def extract_returns(docstring: str) -> Dict[str, str]:
    m = _CPP_RETURNS_RE.search(docstring)
    if m:
        return {"type": "", "description": m.group(1).strip()}
    return {"type": "", "description": ""}
def extract_business_rules(docstring: str) -> List[str]:
    rules: List[str] = []
    # 1. Extract @brief if present
    brief_m = _CPP_BRIEF_RE.search(docstring)
    if brief_m:
        rules.append(brief_m.group(1).strip())

    # 2. Extract lines with business-logic keywords
    lines = docstring.splitlines()
    for line in lines:
        stripped = line.strip().lstrip("/* ").rstrip("*/ ").lstrip("* ")
        if "@brief" in line:
            continue
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only", "calculation", "multiply", "logic"]):
            rules.append(stripped)
    return rules
