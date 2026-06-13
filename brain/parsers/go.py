import re
from typing import List

_GO_COMMENT_RE = re.compile(r"^//\s*(.+)$", re.MULTILINE)

def extract_params(docstring: str) -> List[dict]:
    # Go comments are usually unstructured
    return []

def extract_returns(docstring: str) -> dict:
    return {"type": "", "description": ""}

def extract_business_rules(docstring: str) -> List[str]:
    """Extract meaningful lines from Go comment blocks (// ...)."""
    lines = _GO_COMMENT_RE.findall(docstring)
    # Simple heuristic: lines with more than 5 words or containing keywords
    return [l for l in lines if len(l) > 5]
