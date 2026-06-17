import re
from typing import Dict, List, Any

_PHP_PARAM_RE = re.compile(
    r"@param\s+(?:\{([^}]*)\}\s+)?\$(\w+)\s+(.*)", re.IGNORECASE
)
_PHP_RETURNS_RE = re.compile(
    r"@returns?\s+(?:\{([^}]*)\}\s+)?(.*)", re.IGNORECASE
)

def _parse_php_docstring(docstring: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"_main": []}
    current_section = "_main"
    for line in docstring.splitlines():
        stripped = line.strip().lstrip("/* ").rstrip("*/ ")
        if not stripped: continue
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
        params.append({"name": f"${m.group(2)}", "type": m.group(1) or "", "description": m.group(3).strip()})
    return params

def extract_returns(docstring: str) -> Dict[str, str]:
    m = _PHP_RETURNS_RE.search(docstring)
    return {"type": m.group(1) or "", "description": m.group(2).strip()} if m else {"type": "", "description": ""}

def extract_business_rules(docstring: str) -> List[str]:
    sections = _parse_php_docstring(docstring)
    rules: List[str] = []
    for r in sections.get("rule", []): rules.append(r.replace("@rule", "").strip())
    for line in sections.get("_main", []):
        stripped = line.strip()
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only"]):
            rules.append(stripped)
    return rules

def extract_dataflow(code_snippet: str) -> List[Dict[str, Any]]:
    """
    Heuristic dataflow extraction for PHP.
    Identifies sources, sanitizers, sinks, and synthesized calls with high-fidelity.
    """
    dataflow = []
    constants = {}
    
    # Pre-scan for defines to ensure they are available for all lines
    for match in re.finditer(r"\bdefine\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", code_snippet):
        constants[match.group(1)] = match.group(2)

    lines = code_snippet.splitlines()
    for i, line in enumerate(lines):
        pos = code_snippet.find(line)
        
        # 0. Conditions and Branches
        m_cond = re.search(r"\b(if|elseif|switch|while|for|foreach)\b\s*\((.*)\)", line)
        if m_cond:
            dataflow.append({"type": "condition", "verb": m_cond.group(1), "content": m_cond.group(2), "pos": pos + m_cond.start()})
        
        m_else = re.search(r"\belse\b", line)
        if m_else and not m_cond:
            dataflow.append({"type": "condition", "verb": "else", "content": "else branch", "pos": pos + m_else.start()})
            
        m_case = re.search(r"\bcase\b\s*([^:]+):", line)
        if m_case:
            dataflow.append({"type": "condition", "verb": "case", "content": m_case.group(1).strip(), "pos": pos + m_case.start()})

        # 1. Constants (Record as sink for behavior)
        m = re.search(r"\bdefine\s*\(\s*['\"](\w+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", line)
        if m:
            dataflow.append({"type": "sink", "sink": "define", "args": f"{m.group(1)}, {m.group(2)}", "pos": pos + m.start()})

        # 1. Sources
        for m in re.finditer(r"\$_(SESSION|COOKIE|GET|POST|REQUEST|SERVER|FILES)\s*\[\s*['\"](\w+)['\"]\s*\]", line):
            dataflow.append({"type": "source", "variable": f"$_{m.group(1)}['{m.group(2)}']", "pos": pos + m.start()})

        # 2. Assignments
        m = re.search(r"(?<!['\"\w\$])(\$[\w\->\[\]'\" ]+)\s*([\.\+\-\*\/]?=)\s*([^;]+);", line)
        if m:
            dataflow.append({"type": "assignment", "variable": m.group(1).strip(), "operation": m.group(2), "value": m.group(3).strip(), "pos": pos + m.start()})

        # 3. Includes / Requires
        m = re.search(r"\b(include_once|require_once|include|require)\b\s*\(?([^;]+)\)?\s*;", line)
        if m:
            verb, raw_path = m.group(1), m.group(2).strip().rstrip(")")
            hint = raw_path
            for cname, cval in constants.items():
                if cname in hint: hint = hint.replace(cname, cval)
            
            # Clean up hint for resolution: remove concatenation dots and quotes
            # e.g. ../../ . 'dvwa/...' -> ../../dvwa/...
            clean_hint = re.sub(r"['\"\s\.]", "", hint)
            dataflow.append({"type": "synthesized_call", "verb": verb, "raw_path": raw_path, "resolved_hint": clean_hint, "pos": pos + m.start()})
            dataflow.append({"type": "sink", "sink": verb, "args": raw_path, "pos": pos + m.start()})

        # 4. Custom Calls
        keywords = {"if", "elseif", "else", "switch", "case", "for", "while", "foreach", "return", "break", "continue", "exit", "die", "echo", "print", "isset", "unset", "empty", "array", "define", "include", "require", "include_once", "require_once"}
        for m in re.finditer(r"\b([a-zA-Z_\x7f-\xff][a-zA-Z0-9_\x7f-\xff]*)\b\s*\(", line):
            func_name = m.group(1)
            if func_name in keywords: continue
            
            rest = line[m.end():]
            # Handle nested parentheses by counting or greedy until semicolon
            args = rest.split(";", 1)[0].rsplit(")", 1)[0].strip()
            
            is_significant = (
                not func_name[0].islower() or 
                "_" in func_name or 
                any(c.isupper() for c in func_name[1:]) or
                func_name in ["mysqli_query", "eval", "exec", "system"]
            )
            
            if is_significant:
                clean_args = re.sub(r'["\'].*?["\']', '"..."', args).replace("\n", " ")
                dataflow.append({"type": "sink", "sink": func_name, "args": clean_args, "pos": pos + m.start()})

    for m in re.finditer(r"[{}]", code_snippet):
        dataflow.append({"type": "delimiter", "value": m.group(0), "pos": m.start()})

    dataflow.sort(key=lambda x: x.get("pos", 0))
    return dataflow
