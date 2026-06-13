import re
from typing import Dict, List

_RUST_LINE_RE = re.compile(r"^///?!?\s*(.*)$", re.MULTILINE)
_RUST_ARGS_BLOCK_RE = re.compile(r"#\s*Arguments\s*\n((?:.|\n)*?)(?=#\s|\Z)", re.IGNORECASE)
_RUST_ARG_ITEM_RE = re.compile(r"\*\s+`(\w+)`\s+-\s+(.*)")
_RUST_RETURNS_BLOCK_RE = re.compile(r"#\s*Returns\s*\n((?:.|\n)*?)(?=#\s|\Z)", re.IGNORECASE)

def extract_params(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    block_m = _RUST_ARGS_BLOCK_RE.search(docstring)
    if block_m:
        content = block_m.group(1)
        for m in _RUST_ARG_ITEM_RE.finditer(content):
            params.append({
                "name": m.group(1),
                "type": "",
                "description": m.group(2).strip()
            })
    return params

def extract_returns(docstring: str) -> Dict[str, str]:
    block_m = _RUST_RETURNS_BLOCK_RE.search(docstring)
    desc = block_m.group(1).strip() if block_m else ""
    return {"type": "", "description": desc}

def _extract_module_comments(docstring: str) -> List[str]:
    """Extract top-level module comments in Rust (/// or //!)."""
    block_m = _RUST_LINE_RE.findall(docstring)
    return [l for l in block_m if l]

def extract_business_rules(docstring: str) -> List[str]:
    lines = _extract_module_comments(docstring)
    rules: List[str] = []
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only"]):
            rules.append(stripped)
    return rules
