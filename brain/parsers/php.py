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
    for match in re.finditer(r"\$_(SESSION|COOKIE|GET|POST|REQUEST|SERVER|FILES)\[['\"](\w+)['\"]\]", code_snippet):
        dataflow.append({
            "type": "global_state",
            "variable": f"$_{match.group(1)}['{match.group(2)}']",
            "source": f"_{match.group(1)}",
            "pos": match.start()
        })

    # 2. Assignments
    # Supports $var, $obj->prop, $arr['key']
    assign_pattern = re.compile(r"(?<!['\"\w\$])(\$[\w\->\[\]'\" ]+)\s*([\.\+\-\*\/]?=)\s*([^;]+);")
    for match in assign_pattern.finditer(code_snippet):
        dataflow.append({
            "type": "assignment",
            "variable": match.group(1).strip(),
            "operation": match.group(2),
            "value": match.group(3).strip(),
            "pos": match.start()
        })
    include_pattern = re.compile(r"(?<!['\"\w\$])\b(include|require)(_once)?\b\s*\(?(['\"].*?['\"]|[^;]{1,100})\)?\s*;", re.IGNORECASE)
    for match in include_pattern.finditer(code_snippet):
        path = match.group(3).strip()
        # Heuristics to avoid capturing text as paths
        if any(x in path for x in ["<", ">", "\n", "  "]) or len(path) < 2:
            continue
        dataflow.append({
            "type": "synthesized_call",
            "verb": match.group(1),
            "raw_path": path,
            "pos": match.start()
        })

    # 4. Sinks
    sink_pattern = re.compile(r"(?<!['\"\w\$])\b(echo|print|query|die|header|setcookie|mysqli_query|mysqli_prepare|eval|exec|system|shell_exec)\b\s*\(?([^;)]{1,200})\)?\s*;")
    for match in sink_pattern.finditer(code_snippet):
        args = match.group(2).strip()
        if len(args) > 200 or "\n" in args:
             args = args[:197] + "..."
        dataflow.append({
            "type": "sink",
            "sink": match.group(1),
            "args": args,
            "pos": match.start()
        })

    # 5. Config & UI Transitions (SURFACE CRITICAL ASSIGNMENTS)
    critical_vars = ["$headerCSP", "$page['body']", "$html", "$PHPUploadPath"]
    for match in assign_pattern.finditer(code_snippet):
        var = match.group(1).strip()
        val = match.group(3).strip()
        if any(cv in var for buf in critical_vars for cv in [buf]):
            # Add as a synthesized call to make it a state in the map
            label = val.replace("\n", " ")
            if len(label) > 100: label = label[:97] + "..."
            dataflow.append({
                "type": "synthesized_call",
                "verb": "Set " + var.replace("$", ""),
                "raw_path": label,
                "pos": match.start()
            })

    # 5. Conditions (Decision Points)
    cond_pattern = re.compile(r"\b(if|elseif|else if|case)\b\s*\(?([^){:]+)\)?")
    for match in cond_pattern.finditer(code_snippet):
        dataflow.append({
            "type": "condition",
            "verb": match.group(1),
            "content": match.group(2).strip(),
            "pos": match.start()
        })

    # Sort by position to maintain order
    dataflow.sort(key=lambda x: x.get("pos", 0))
        
    return dataflow