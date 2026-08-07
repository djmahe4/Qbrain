import re
from typing import Dict, List, Any

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

def extract_dataflow(code_snippet: str) -> List[Dict[str, Any]]:
    """
    Identifies variable assignments, usages, and control flow in Python.
    Synthesizes standard { and } block delimiters based on Python indentation.
    """
    dataflow = []
    lines = code_snippet.splitlines(keepends=True)
    line_starts = [0]
    for line in lines:
        line_starts.append(line_starts[-1] + len(line))
        
    def get_line(pos):
        import bisect
        return bisect.bisect_right(line_starts, pos)

    indent_stack = []
    current_pos = 0

    for idx, line in enumerate(lines, 1):
        line_stripped = line.lstrip()
        if not line_stripped or line_stripped.startswith("#"):
            current_pos += len(line)
            continue
            
        # Calculate indentation depth
        indent_depth = len(line) - len(line_stripped)
        
        # Synthesize block closing delimiters if indentation decreased
        while indent_stack and indent_depth < indent_stack[-1]:
            indent_stack.pop()
            dataflow.append({
                "type": "delimiter",
                "value": "}",
                "pos": current_pos,
                "line": idx
            })
            
        # 1. Parameter extraction from def pattern
        def_match = re.match(r"^def\s+\w+\s*\(([^)]*)\)", line_stripped)
        if def_match:
            params = def_match.group(1).split(",")
            for p in params:
                p_name = p.split("=")[0].split(":")[0].strip()
                if p_name and p_name not in ("self", "cls"):
                    dataflow.append({
                        "type": "assignment",
                        "variable": p_name,
                        "operation": "=",
                        "value": "param_input",
                        "pos": current_pos + def_match.start(1),
                        "line": idx
                    })
            # Start of function body indentation tracking
            indent_stack.append(indent_depth)
            dataflow.append({
                "type": "delimiter",
                "value": "{",
                "pos": current_pos + len(line),
                "line": idx + 1
            })

        # 2. Assignment detection (e.g. x = val)
        assign_match = re.match(r"^(\w+)\s*(=|\+=|-=|\*=)\s*(.+)$", line_stripped)
        if assign_match and not line_stripped.startswith("def "):
            dataflow.append({
                "type": "assignment",
                "variable": assign_match.group(1),
                "operation": assign_match.group(2),
                "value": assign_match.group(3).strip(),
                "pos": current_pos + assign_match.start(1),
                "line": idx
            })
            
        # 3. Control flow condition matching (e.g. if x > 10:)
        cond_match = re.match(r"^(if|elif|while|for)\b\s*(.+):$", line_stripped)
        if cond_match:
            cond_val = cond_match.group(2).strip()
            dataflow.append({
                "type": "condition",
                "verb": cond_match.group(1),
                "content": cond_val,
                "pos": current_pos + cond_match.start(2),
                "line": idx
            })
            indent_stack.append(indent_depth)
            dataflow.append({
                "type": "delimiter",
                "value": "{",
                "pos": current_pos + len(line),
                "line": idx + 1
            })
            
        # 4. Raises and Returns
        interrupt_match = re.match(r"^(return|raise)\b\s*(.*)$", line_stripped)
        if interrupt_match:
            dataflow.append({
                "type": "interrupt",
                "value": interrupt_match.group(1),
                "pos": current_pos,
                "line": idx
            })
            
        current_pos += len(line)

    # Pop remaining block scopes
    while indent_stack:
        indent_stack.pop()
        dataflow.append({
            "type": "delimiter",
            "value": "}",
            "pos": current_pos,
            "line": len(lines)
        })

    dataflow.sort(key=lambda x: x.get("pos", 0))
    return dataflow

