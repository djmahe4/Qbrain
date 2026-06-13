import re
from typing import Dict, List

_NATSPEC_NOTICE_RE = re.compile(r"@notice\s+(.+)", re.IGNORECASE)
_NATSPEC_DEV_RE = re.compile(r"@dev\s+(.+)", re.IGNORECASE)
_NATSPEC_PARAM_RE = re.compile(r"@param\s+(\w+)\s+(.*)", re.IGNORECASE)
_NATSPEC_RETURN_RE = re.compile(r"@return\s+(?:(\w+)\s+)?(.*)", re.IGNORECASE)

def extract_params(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    for m in _NATSPEC_PARAM_RE.finditer(docstring):
        params.append({
            "name": m.group(1),
            "type": "",
            "description": m.group(2).strip()
        })
    return params

def extract_returns(docstring: str) -> Dict[str, str]:
    m = _NATSPEC_RETURN_RE.search(docstring)
    if m:
        return {
            "type": "",
            "description": m.group(2).strip()
        }
    return {"type": "", "description": ""}

def extract_business_rules(docstring: str) -> List[str]:
    rules: List[str] = []
    for m in _NATSPEC_NOTICE_RE.finditer(docstring):
        rules.append(m.group(1).strip())
    for m in _NATSPEC_DEV_RE.finditer(docstring):
        rules.append(m.group(1).strip())
    return rules
