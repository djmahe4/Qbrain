import re
import bisect
from typing import Dict, List, Any

def mask_strings_and_comments(code: str) -> str:
    masked = list(code)
    n = len(code)
    i = 0
    in_str = False
    str_char = None
    escaped = False
    
    while i < n:
        char = code[i]
        
        def mask_char(idx):
            if code[idx] not in ('\n', '\r'):
                masked[idx] = ' '
                
        if in_str:
            if escaped:
                escaped = False
                mask_char(i)
            elif char == '\\':
                escaped = True
                mask_char(i)
            elif char == str_char:
                in_str = False
            else:
                mask_char(i)
            i += 1
            continue
            
        if i + 1 < n and code[i:i+2] == '/*':
            mask_char(i)
            mask_char(i+1)
            i += 2
            while i < n:
                if i + 1 < n and code[i:i+2] == '*/':
                    mask_char(i)
                    mask_char(i+1)
                    i += 2
                    break
                else:
                    mask_char(i)
                    i += 1
            continue
            
        if i + 1 < n and code[i:i+2] == '//':
            mask_char(i)
            mask_char(i+1)
            i += 2
            while i < n and code[i] not in ('\n', '\r'):
                mask_char(i)
                i += 1
            continue
            
        if char == '#':
            mask_char(i)
            i += 1
            while i < n and code[i] not in ('\n', '\r'):
                mask_char(i)
                i += 1
            continue
            
        if char in ('"', "'"):
            in_str = True
            str_char = char
            i += 1
            continue
            
        i += 1
        
    return "".join(masked)

_PHP_PARAM_RE = re.compile(
    r"@param\s+(?:\{([^}]*)\}\s+)?\$(\w+)\s+(.*)", re.IGNORECASE
)
_PHP_RETURNS_RE = re.compile(
    r"@returns?\s+(?:\{([^}]*)\}\s+)?(.*)", re.IGNORECASE
)

def extract_classes(code: str) -> List[Dict[str, Any]]:
    """
    Extracts class, interface, and enum definitions along with their properties and methods.
    """
    entities = []
    # Matches class, interface, enum
    class_pattern = re.compile(r"\b(class|interface|enum)\s+(\w+)\s*(?:extends\s+[\w\\]+)?\s*(?:implements\s+[\w\\]+(?:\s*,\s*[\w\\]+)*)?\s*\{", re.IGNORECASE)
    
    # Find all classes and their contents
    for match in class_pattern.finditer(code):
        kind = match.group(1).capitalize()
        name = match.group(2)
        start_pos = match.start()
        
        # Find matching closing brace (simple count)
        brace_count = 0
        end_pos = -1
        for i in range(match.end() - 1, len(code)):
            if code[i] == '{': brace_count += 1
            elif code[i] == '}': brace_count -= 1
            if brace_count == 0:
                end_pos = i + 1
                break
        
        if end_pos != -1:
            class_code = code[match.end():end_pos-1]
            
            # Extract properties
            properties = {}
            # Matches: public|private|protected [static] $name [= value];
            # Matches: [visibility] [static] [type] $name [= value];
            prop_pattern = re.compile(r"\b(public|private|protected|var)?\s+(?:static\s+)?(?:\??\w+\s+)?\$(\w+)\s*(?:=\s*([^;]+))?;", re.IGNORECASE | re.DOTALL)
            for p_match in prop_pattern.finditer(class_code):
                vis = p_match.group(1) or "public"
                if vis.lower() == "var": vis = "public"
                p_name = p_match.group(2)
                val = p_match.group(3).strip() if p_match.group(3) else "null"
                val = re.sub(r"\s+", " ", val) # Flatten multiline values
                properties[p_name] = {"visibility": vis, "default": val}
            
            # Extract methods (simplified)
            methods = []
            # Matches: [visibility] [static] function name (
            method_pattern = re.compile(r"\b(?:(public|private|protected)\s+)?(?:static\s+)?function\s+(\w+)\s*\(", re.IGNORECASE)
            for m_match in method_pattern.finditer(class_code):
                methods.append(m_match.group(2))
            
            entities.append({
                "kind": kind,
                "name": name,
                "properties": properties,
                "methods": methods,
                "pos": start_pos,
                "end_pos": end_pos
            })
    return entities

def extract_globals(code: str) -> Dict[str, Any]:
    """
    Extracts global constants and environment configurations from PHP setup files.
    """
    globals_data = {}

    # define('NAME', 'VALUE')
    define_pattern = re.compile(r"define\s*\(\s*['\"](\w+)['\"]\s*,\s*(['\"].*?['\"]|[^,)]+)\s*\)", re.IGNORECASE)
    for match in define_pattern.finditer(code):
        name = match.group(1)
        value = match.group(2).strip().strip("'\"")
        globals_data[name] = value

    # const NAME = 'VALUE'
    const_pattern = re.compile(r"\bconst\s+(\w+)\s*=\s*(['\"].*?['\"]|[^;]+);", re.IGNORECASE)
    for match in const_pattern.finditer(code):
        name = match.group(1)
        value = match.group(2).strip().strip("'\"")
        globals_data[name] = value

    # Global array initializations like $_CONFIG['key'] = 'value'
    # Or $GLOBALS['key'] = 'value'
    global_init_pattern = re.compile(r"(\$_(SESSION|CONFIG|ENV|SERVER)|(?:\$GLOBALS))\[['\"](\w+)['\"]\]\s*=\s*(['\"].*?['\"]|[^;]+);", re.IGNORECASE)
    for match in global_init_pattern.finditer(code):
        array_name = match.group(1)
        key = match.group(3)
        value = match.group(4).strip().strip("'\"")
        globals_data[f"{array_name}['{key}']"] = value

    return globals_data

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
    for r in sections.get("rule", []):
        rules.append(r.replace("@rule", "").strip())
    main = sections.get("_main", [])
    for line in main:
        stripped = line.strip()
        if len(stripped) > 10 and any(kw in stripped.lower() for kw in ["must", "should", "ensure", "valid", "check", "verify", "only"]):
            rules.append(stripped)
    return rules

def extract_dataflow(code_snippet: str, redirectors: List[str] = None) -> List[Dict[str, Any]]:
    """
    Identifies variable assignments, usages, and synthesized dependencies in PHP.
    Enhanced with line numbers and scenario-driven decision points.
    """
    dataflow = []
    
    # Line number mapping
    lines = code_snippet.splitlines(keepends=True)
    line_starts = [0]
    for line in lines:
        line_starts.append(line_starts[-1] + len(line))
    def get_line(pos): return bisect.bisect_right(line_starts, pos)

    masked_code = mask_strings_and_comments(code_snippet)

    # 1. Globals Detection
    # Security Level Detection (DVWA-specific heuristic)
    if "DVWA" in code_snippet:
        sec_pattern = re.compile(r"DVWA_WEB_PAGE_TO_ROOT\s*=\s*['\"](.*?)['\"]")
        # Scan for security level changes in session or DB config if applicable
        # This is a heuristic to trigger behavior splitting
        sec_level_check = re.search(r"if\s*\(\s*.*?security_level.*?==\s*['\"](\w+)['\"]", code_snippet, re.IGNORECASE)
        if sec_level_check:
            dataflow.append({
                "type": "scenario_switch",
                "variable": "security_level",
                "value": sec_level_check.group(1),
                "pos": sec_level_check.start(),
                "line": get_line(sec_level_check.start())
            })

    # 0. Parameters Detection
    param_pattern = re.compile(r"function\s+\w+\s*\(([^)]*)\)")
    for match in param_pattern.finditer(masked_code):
        params = code_snippet[match.start(1):match.end(1)].split(",")
        for p in params:
            p = p.strip()
            if p.startswith("$"):
                dataflow.append({
                    "type": "assignment",
                    "variable": p,
                    "operation": "=",
                    "value": "$_GET['external_input']",
                    "pos": match.start(),
                    "line": get_line(match.start())
                })

    for match in re.finditer(r"\$_(SESSION|COOKIE|GET|POST|REQUEST|SERVER|FILES)\[['\"](\w+)['\"]\]", code_snippet):
        if masked_code[match.start()] == ' ': continue
        dataflow.append({
            "type": "global_state",
            "variable": f"$_{match.group(1)}['{match.group(2)}']",
            "source": f"_{match.group(1)}",
            "pos": match.start(),
            "line": get_line(match.start())
        })

    # 1.2 Class and Property Detection
    for entity in extract_classes(code_snippet):
        kind = entity["kind"]
        dataflow.append({
            "type": "symbol_definition",
            "kind": kind,
            "variable": entity["name"],
            "properties": entity["properties"],
            "methods": entity["methods"],
            "pos": entity["pos"],
            "line": get_line(entity["pos"])
        })
        # Register properties as global_state-like entities if they are part of a Class symbol
        for p_name, p_info in entity["properties"].items():
            dataflow.append({
                "type": "global_state",
                "variable": f"{entity['name']}::${p_name}",
                "source": "internal",
                "pos": entity["pos"],
                "line": get_line(entity["pos"])
            })

    # 1.1 Constants Detection (define and const)
    define_pattern = re.compile(r"define\s*\(\s*['\"](\w+)['\"]\s*,\s*(['\"].*?['\"]|[^,)]+)\s*\)", re.IGNORECASE)
    for match in define_pattern.finditer(code_snippet):
        if masked_code[match.start()] == ' ': continue
        dataflow.append({
            "type": "constant",
            "variable": match.group(1),
            "value": match.group(2).strip().strip("'\""),
            "pos": match.start(),
            "line": get_line(match.start())
        })

    const_pattern = re.compile(r"\bconst\s+(\w+)\s*=\s*(['\"].*?['\"]|[^;]+);", re.IGNORECASE)
    for match in const_pattern.finditer(code_snippet):
        if masked_code[match.start()] == ' ': continue
        dataflow.append({
            "type": "constant",
            "variable": match.group(1),
            "value": match.group(2).strip().strip("'\""),
            "pos": match.start(),
            "line": get_line(match.start())
        })

    # 2. Assignments
    assign_pattern = re.compile(r"(?<!['\"\w\$])(\$[\w\->\[\]'\" ]+)\s*([\.\+\-\*\/]?=)\s*([^;]+);")
    for match in assign_pattern.finditer(masked_code):
        dataflow.append({
            "type": "assignment",
            "variable": code_snippet[match.start(1):match.end(1)].strip(),
            "operation": match.group(2),
            "value": code_snippet[match.start(3):match.end(3)].strip(),
            "pos": match.start(),
            "line": get_line(match.start())
        })

    # 3. Includes / Requires
    include_pattern = re.compile(r"(?<!['\"\w\$])\b(include|require)(_once)?\b\s*\(?(['\"].*?['\"]|[^;]{1,100})\)?\s*;", re.IGNORECASE)
    for match in include_pattern.finditer(masked_code):
        path = code_snippet[match.start(3):match.end(3)].strip()
        if any(x in path for x in ["<", ">", "\n", "  "]) or len(path) < 2: continue
        dataflow.append({
            "type": "synthesized_call",
            "verb": match.group(1),
            "raw_path": path,
            "pos": match.start(),
            "line": get_line(match.start())
        })

    # 4. Sinks & Redirections
    sink_pattern = re.compile(r"(?<!['\"\w\$])\b(echo|print|query|die|header|setcookie|mysqli_query|mysqli_prepare|eval|exec|system|shell_exec)\b\s*\(?([^;)\n]{1,200})\)?", re.IGNORECASE)
    for match in sink_pattern.finditer(masked_code):
        sink = match.group(1).lower()
        args = code_snippet[match.start(2):match.end(2)].strip()
        
        # Specialized check for header("Location: ...")
        if sink == "header":
            loc_match = re.search(r"Location:\s*(['\"].*?['\"]|[^'\"\s]+)", args, re.IGNORECASE)
            if loc_match:
                dataflow.append({
                    "type": "synthesized_call",
                    "verb": "redirect",
                    "raw_path": loc_match.group(1).strip().strip("'\""),
                    "pos": match.start(),
                    "line": get_line(match.start())
                })
        # 5. Sink Atom Generation
        dataflow.append({
            "type": "sink",
            "sink": sink,
            "args": args,
            "pos": match.start(),
            "line": get_line(match.start())
        })

    # 5. Generic calls for dynamic detection
    call_pattern = re.compile(r"(?<!['\"\w\$])(?!\b(if|elseif|else|switch|for|while|foreach|echo|print|die|include|require|header|setcookie|mysqli_query|mysqli_prepare|eval|exec|system|shell_exec)\b)(\w+)\s*\(([^;)\n]{0,200})\)", re.IGNORECASE)
    for match in call_pattern.finditer(masked_code):
        func_name = match.group(2)
        args = code_snippet[match.start(3):match.end(3)].strip()
        
        # Dynamic redirection detection (Heuristic + Registry)
        is_redirect = False
        if redirectors and func_name in redirectors:
            is_redirect = True
        elif "redirect" in func_name.lower():
            is_redirect = True

        if is_redirect:
            dataflow.append({
                "type": "synthesized_call",
                "verb": "redirect",
                "raw_path": args.strip().strip("'\""),
                "pos": match.start(),
                "line": get_line(match.start())
            })
        else:
            dataflow.append({
                "type": "call",
                "function": func_name,
                "args": args,
                "pos": match.start(),
                "line": get_line(match.start())
            })

    # 5. Conditions & Branches (Decision Points)
    cond_pattern = re.compile(r"\b(if|elseif|else if|else|switch|case|default|for|while|foreach)\b(?:\s*\(?([^{:\n]+))?")
    for match in cond_pattern.finditer(masked_code):
        verb = match.group(1)
        content = ""
        if match.group(2):
            content = code_snippet[match.start(2):match.end(2)].strip()
        if content.endswith(')'): content = content[:-1].strip()
        if content.endswith(':'): content = content[:-1].strip()
        content = content.replace("\n", " ").replace("\r", "")
        if len(content) > 150: content = content[:147] + "..."
        dataflow.append({
            "type": "condition",
            "verb": verb,
            "content": content,
            "pos": match.start(),
            "line": get_line(match.start())
        })
        if verb == "switch" and content.startswith("$"):
            dataflow.append({
                "type": "usage",
                "variable": content,
                "pos": match.start(),
                "line": get_line(match.start())
            })

    # 5.5 Case-specific isolation: ensure case/default atoms are clean
    for atom in dataflow:
        if atom.get("type") == "condition" and atom.get("verb") in ("case", "default"):
            atom["content"] = atom["content"].strip(": ")

    # 5.6 Variable Usage Detection (for linking behaviors without assignments)
    usage_pattern = re.compile(r"(?<!['\"\w\$])(\$[a-zA-Z_\x7f-\xff][a-zA-Z0-9_\x7f-\xff]*)")
    for match in usage_pattern.finditer(masked_code):
        var_name = match.group(1)
        # Check if already tracked in assignments or global state
        if any(a.get("variable") == var_name for a in dataflow): continue
        
        dataflow.append({
            "type": "usage",
            "variable": var_name,
            "pos": match.start(),
            "line": get_line(match.start())
        })

    # 6. Block Delimiters
    for match in re.finditer(r"[{}]", masked_code):
        dataflow.append({
            "type": "delimiter",
            "value": match.group(0),
            "pos": match.start(),
            "line": get_line(match.start())
        })

    # 7. Control Flow Interrupts
    for match in re.finditer(r"\b(break|return)\b\s*;?", masked_code):
        dataflow.append({
            "type": "interrupt",
            "value": match.group(1),
            "pos": match.start(),
            "line": get_line(match.start())
        })

    dataflow.sort(key=lambda x: x.get("pos", 0))
    return dataflow
