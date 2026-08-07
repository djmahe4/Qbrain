"""
brain/language_parser.py
Multi-language docstring parser supporting Python, JS/TS (JSDoc), Solidity (NatSpec), Go, Rust.

Produces a DocstringGenome dict:
{
    name: str,
    signature: str,
    docstring: str,
    language: str,
    params: List[{name, type, description}],
    returns: {type, description},
    business_rules: List[str],
    dataflow: List[Dict[str, str]],
    variables: List[str]
}
"""
import re
from typing import Any, Dict, List, Optional


# ─────────────────────────── Language detection ───────────────────────────

_EXTENSION_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".sol": "solidity",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "cpp",
    ".cpp": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
}



def detect_language(file_path: str) -> str:
    """Return language identifier from file extension, or 'generic' if unknown."""
    if not file_path:
        return "generic"
    for ext, lang in _EXTENSION_MAP.items():
        if file_path.endswith(ext):
            return lang
    return "generic"


from brain.parsers import python, javascript, solidity, go, rust, cpp, php

def extract_dataflow(code_snippet: str, language: str) -> List[Dict[str, Any]]:
    """Extract dataflow information from code snippets across multiple languages."""
    if not code_snippet:
        return []
    
    lang = language.lower()
    if lang == "php":
        return php.extract_dataflow(code_snippet)
    if lang == "python":
        return python.extract_dataflow(code_snippet)
    if lang in ("javascript", "typescript"):
        return javascript.extract_dataflow(code_snippet)
        
    # Helper to parse general brace-based languages (Rust, Go, Solidity, C++)
    dataflow = []
    lines = code_snippet.splitlines(keepends=True)
    line_starts = [0]
    for line in lines:
        line_starts.append(line_starts[-1] + len(line))
        
    def get_line(pos):
        import bisect
        return bisect.bisect_right(line_starts, pos)

    current_pos = 0
    for idx, line in enumerate(lines, 1):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("//") or line_stripped.startswith("/*") or line_stripped.startswith("///"):
            current_pos += len(line)
            continue
            
        # 1. Delimiters
        for char_idx, char in enumerate(line_stripped):
            if char in ("{", "}"):
                dataflow.append({
                    "type": "delimiter",
                    "value": char,
                    "pos": current_pos + char_idx,
                    "line": idx
                })
                
        # 2. Parameters from function declaration
        if lang == "rust":
            func_match = re.match(r"^fn\s+\w+\s*(?:<[^>]+>)?\s*\(([^)]*)\)", line_stripped)
        elif lang == "go":
            func_match = re.match(r"^func\s+\w+\s*\(([^)]*)\)", line_stripped)
        elif lang == "solidity":
            func_match = re.match(r"^function\s+\w+\s*\(([^)]*)\)", line_stripped)
        else: # cpp
            func_match = re.match(r"^\w+\s+\w+\s*\(([^)]*)\)", line_stripped)
            
        if func_match:
            params = func_match.group(1).split(",")
            for p in params:
                p = p.strip()
                if not p: continue
                # Parse variable name from param declaration (x: i32, val int, uint256 val)
                if lang == "rust" and ":" in p:
                    p_name = p.split(":")[0].strip()
                elif lang == "go" and " " in p:
                    p_name = p.split()[0].strip()
                elif lang == "solidity" and " " in p:
                    p_name = p.split()[-1].strip()
                elif lang == "cpp" and " " in p:
                    p_name = p.split()[-1].strip()
                else:
                    p_name = p
                    
                if p_name and p_name not in ("self", "cls"):
                    dataflow.append({
                        "type": "assignment",
                        "variable": p_name,
                        "operation": "=",
                        "value": "param_input",
                        "pos": current_pos + func_match.start(1),
                        "line": idx
                    })

        # 3. Variable assignments
        assign_match = None
        if lang == "rust":
            assign_match = re.match(r"^let\s+(?:mut\s+)?(\w+)\s*=\s*(.+)$", line_stripped)
        elif lang == "go":
            assign_match = re.match(r"^(\w+)\s*:=\s*(.+)$", line_stripped) or re.match(r"^var\s+(\w+)\s*=\s*(.+)$", line_stripped)
        elif lang == "solidity":
            assign_match = re.match(r"^(?:uint256|address|bool|string|bytes\d*)\s+(\w+)\s*=\s*(.+)$", line_stripped)
        elif lang == "cpp":
            assign_match = re.match(r"^(?:int|float|double|char|bool|auto|std::string)\s+(\w+)\s*=\s*(.+)$", line_stripped)
            
        if assign_match:
            dataflow.append({
                "type": "assignment",
                "variable": assign_match.group(1),
                "operation": "=",
                "value": assign_match.group(2).strip().strip(";"),
                "pos": current_pos + assign_match.start(1),
                "line": idx
            })
        else:
            # Fallback assignment (x = val)
            fallback_assign = re.match(r"^(\w+)\s*(=|\+=|-=)\s*(.+)$", line_stripped)
            # Make sure it's not a control flow keyword
            if fallback_assign and fallback_assign.group(1) not in ("if", "for", "while", "return", "require", "revert"):
                dataflow.append({
                    "type": "assignment",
                    "variable": fallback_assign.group(1),
                    "operation": fallback_assign.group(2),
                    "value": fallback_assign.group(3).strip().strip(";"),
                    "pos": current_pos + fallback_assign.start(1),
                    "line": idx
                })

        # 4. Conditions
        cond_match = re.search(r"\b(if|while|for)\b\s*(?:\((.+)\)|(.+))", line_stripped)
        if cond_match:
            cond_val = cond_match.group(2) or cond_match.group(3)
            cond_val = cond_val.strip().strip("{").strip()
            dataflow.append({
                "type": "condition",
                "verb": cond_match.group(1),
                "content": cond_val,
                "pos": current_pos + cond_match.start(0),
                "line": idx
            })

        # 5. Interrupts
        interrupt_keywords = ("return", "panic", "throw", "require", "revert", "assert")
        interrupt_match = re.match(fr"^({'|'.join(interrupt_keywords)})\b\s*(.*)$", line_stripped)
        if interrupt_match:
            dataflow.append({
                "type": "interrupt",
                "value": interrupt_match.group(1),
                "pos": current_pos,
                "line": idx
            })

        current_pos += len(line)

    dataflow.sort(key=lambda x: x.get("pos", 0))
    return dataflow


def extract_params(docstring: str, language: str) -> List[Dict[str, str]]:
    """Extract @param / Args sections from a docstring for the given language."""
    if not docstring:
        return []
    
    lang = language.lower()
    if lang == "python":
        return python.extract_params(docstring)
    elif lang == "php":
        return php.extract_params(docstring)
    elif lang in ("javascript", "typescript"):
        return javascript.extract_params(docstring)
    elif lang == "solidity":
        return solidity.extract_params(docstring)
    elif lang == "rust":
        return rust.extract_params(docstring)
    elif lang == "cpp":
        return cpp.extract_params(docstring)
    elif lang == "go":
        return go.extract_params(docstring)
    return []

def extract_returns(docstring: str, language: str) -> Dict[str, str]:
    """Extract @return / Returns section from a docstring for the given language."""
    if not docstring:
        return {"type": "", "description": ""}
    
    lang = language.lower()
    if lang == "python":
        return python.extract_returns(docstring)
    elif lang == "php":
        return php.extract_returns(docstring)
    elif lang in ("javascript", "typescript"):
        return javascript.extract_returns(docstring)
    elif lang == "solidity":
        return solidity.extract_returns(docstring)
    elif lang == "rust":
        return rust.extract_returns(docstring)
    elif lang == "cpp":
        return cpp.extract_returns(docstring)
    elif lang == "go":
        return go.extract_returns(docstring)
    return {"type": "", "description": ""}

def extract_business_rules(docstring: str, language: str) -> List[str]:
    """Extract business logic rules from docstrings."""
    if not docstring:
        return []

    lang = language.lower()
    if lang == "python":
        return python.extract_business_rules(docstring)
    elif lang == "php":
        return php.extract_business_rules(docstring)
    elif lang in ("javascript", "typescript"):
        return javascript.extract_business_rules(docstring)
    elif lang == "solidity":
        return solidity.extract_business_rules(docstring)
    elif lang == "go":
        return go.extract_business_rules(docstring)
    elif lang == "rust":
        return rust.extract_business_rules(docstring)
    elif lang == "cpp":
        return cpp.extract_business_rules(docstring)
    return []


def build_genome(genome_dict: Dict[str, Any]) -> str:
    """
    Build a single semantic genome string from a parsed DocstringGenome dict.
    Concatenates name, signature, docstring, and business rules for embedding.
    """
    name = genome_dict.get("name", "unknown")
    sig = genome_dict.get("signature") or ""
    doc = genome_dict.get("docstring") or ""
    rules = genome_dict.get("business_rules") or []

    if sig:
        if not sig.startswith("("):
            sig = f"({sig})"
    sig_part = sig if sig else ""

    doc_part = ""
    if doc.strip():
        # Strip comment markers
        clean_doc = re.sub(r"[\*/]+", "", doc).strip()
        doc_part = f" — {clean_doc}"

    rules_part = ""
    if rules:
        rules_part = " Rules: " + "; ".join(rules)

    return f"{name}{sig_part}{doc_part}{rules_part}"


# ─────────────────────────── LanguageParser class ───────────────────────────

class LanguageParser:
    """
    Parses a raw MCP graph function record into a structured DocstringGenome dict.
    Supports Python, JS, TS, Solidity, Go, Rust, and generic fallback.
    """

    def parse_coding_standards(self, record: Dict[str, Any]) -> List[str]:
        warnings = []
        name = record.get("name", "")
        code = record.get("code_snippet") or ""
        signature = record.get("signature") or ""
        file_path = record.get("file", "")
        
        symbol_kind = record.get("kind")
        if not symbol_kind and "labels" in record:
            labels = record.get("labels", [])
            _kind_priority = ["Class", "Interface", "Enum", "Variable", "Method", "Function", "Module"]
            symbol_kind = next((k for k in _kind_priority if k in labels), "Function")
        if not symbol_kind:
            symbol_kind = "Function"

        # --- New Architectural & Performance Checks ---
        # 1. Parameter count smell (5+ params in signature)
        if signature:
            # Count params inside outermost parentheses
            if "(" in signature and ")" in signature:
                sig_content = signature.split("(", 1)[1].rsplit(")", 1)[0]
                paren_level = 0
                bracket_level = 0
                brace_level = 0
                in_str = False
                str_char = None
                escaped = False
                current = []
                parts = []
                for char in sig_content:
                    if escaped:
                        escaped = False
                        continue
                    if char == '\\':
                        escaped = True
                        continue
                    if in_str:
                        if char == str_char:
                            in_str = False
                        continue
                    if char in ('"', "'", "`"):
                        in_str = True
                        str_char = char
                        continue
                    if char == '(':
                        paren_level += 1
                    elif char == ')':
                        paren_level -= 1
                    elif char == '[':
                        bracket_level += 1
                    elif char == ']':
                        bracket_level -= 1
                    elif char == '{':
                        brace_level += 1
                    elif char == '}':
                        brace_level -= 1
                    elif char == ',' and paren_level == 0 and bracket_level == 0 and brace_level == 0:
                        parts.append("".join(current).strip())
                        current = []
                        continue
                    current.append(char)
                if current:
                    parts.append("".join(current).strip())
                sig_params = [p for p in parts if p]
                if len(sig_params) >= 5:
                    warnings.append("Parameter count smell: function has 5 or more parameters in signature")

        # 2. File naming and API verb checks
        if file_path:
            normalized_path = file_path.replace("\\", "/")
            path_parts = normalized_path.split("/")
            if len(path_parts) > 1:
                filename = path_parts[-1]
                basename = filename.rsplit(".", 1)[0]
                
                if "components" in path_parts[:-1]:
                    if not re.match(r"^[A-Z][a-zA-Z0-9]*$", basename):
                        warnings.append(f"File in components/ must be PascalCase. Got: {filename}")
                
                if "hooks" in path_parts[:-1]:
                    if not re.match(r"^use[A-Z][a-zA-Z0-9]*$", basename):
                        warnings.append(f"File in hooks/ must be camelCase starting with 'use'. Got: {filename}")

                if "api" in path_parts[:-1]:
                    api_index = path_parts.index("api")
                    subpath_parts = path_parts[api_index + 1:]
                    verbs_to_warn = {"get", "set", "fetch", "delete", "update"}
                    found_verb = False
                    for part in subpath_parts:
                        part_words = re.sub('([A-Z])', r' \1', part)
                        part_words = re.sub(r'[^a-zA-Z0-9]', ' ', part_words).lower().split()
                        for w in part_words:
                            if w in verbs_to_warn:
                                warnings.append(f"API endpoint path uses standard verb '{w}'. Got: {file_path}")
                                found_verb = True
                                break
                        if found_verb:
                            break

        # 3. Code-based performance & validation checks (excluding comments)
        code_no_comments = code
        if code:
            code_no_comments = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
            code_no_comments = re.sub(r'"""\s*.*?\s*"""', '', code_no_comments, flags=re.DOTALL)
            code_no_comments = re.sub(r"'''\s*.*?\s*'''", '', code_no_comments, flags=re.DOTALL)
            code_no_comments = re.sub(r'//.*', '', code_no_comments)
            code_no_comments = re.sub(r'#.*', '', code_no_comments)

        if code_no_comments:
            if re.search(r"\bselect\s*\(\s*['\"]?\*['\"]?\s*\)", code_no_comments, re.IGNORECASE) or re.search(r"\bselect\s+\*", code_no_comments, re.IGNORECASE):
                warnings.append("SQL SELECT * performance check: avoid select('*') or SELECT *")

            if signature and re.search(r"\b(req|request)\b", signature, re.IGNORECASE):
                has_validation = any(kw in code_no_comments.lower() for kw in ["zod", "yup", "joi", "schema", "validate"])
                if not has_validation:
                    warnings.append("Input validation schema check: Request/req parameter is not checked against zod/yup/joi/schema/validate")

            # Type safety check
            if re.search(r':\s*any\b|\bas\s+any\b', code_no_comments):
                warnings.append("Type safety: warn if : any or as any type annotation is used")

            # React state updates check
            for match in re.finditer(r'\bset[A-Z]\w*\((.*?)\)', code_no_comments, re.DOTALL):
                inside = match.group(1)
                if '=>' not in inside and 'function' not in inside:
                    warnings.append("React state updates: warn if a component updates state directly instead of using functional updates")
                    break

            # Empty catch blocks check
            if re.search(r'\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}', code_no_comments):
                warnings.append("Empty catch block: try/catch block contains empty catches (silent failures)")

            # API response format check
            if file_path:
                normalized_path = file_path.replace("\\", "/")
                path_parts = normalized_path.split("/")
                if "api" in path_parts:
                    if re.search(r'\b(?:res|response|Response)\.json\s*\(|\bJSON\.stringify\s*\(', code_no_comments):
                        if "success" not in code_no_comments:
                            warnings.append("API response format check: JSON responses in endpoint files (or methods starting with HTTP verbs under api/ path) must include a 'success' field")


            # --- Vibe Auditor Semantic Checks ---
            # 1. Security critical functions (calls and aliasing)
            risky_symbols = r'(eval|exec|os\.system|subprocess\.(?:run|call|Popen))'
            if re.search(fr'\b{risky_symbols}\s*\(', code_no_comments):
                warnings.append("Security critical: use of eval(), exec(), os.system(), or subprocess is risky")
            
            if re.search(fr'\b\w+\s*=\s*{risky_symbols}\b', code_no_comments):
                warnings.append("Security critical: aliasing risky functions (eval/exec/system) is a common obfuscation tactic")

            # 2. Hardcoded credentials
            if re.search(r'\b(password|secret|api_key|token|credential|auth_key)\b\s*[:=]\s*["\'][^"\']{3,}["\']', code_no_comments, re.IGNORECASE):
                warnings.append("Hardcoded credentials: plain-text secrets or keys detected in code")

            # 3. Insecure defaults
            if re.search(r'\bDEBUG\s*=\s*True\b|\bdebug\s*=\s*True\b', code_no_comments):
                warnings.append("Insecure default: DEBUG=True or debug=True found in code")

            # 4. SQL injection risk
            if re.search(r'\.(?:execute|query)\s*\(\s*(?:f["\']|["\'].*?\+.*?["\'])', code_no_comments, re.IGNORECASE | re.DOTALL):
                warnings.append("SQL injection risk: string concatenation or f-strings in SQL query")

            # 5. Production risks: HTTP timeout
            if 'requests.' in code_no_comments and 'timeout=' not in code_no_comments:
                warnings.append("Production risk: requests call missing a timeout")

            # 6. Unbounded loops
            if 'while True' in code_no_comments and 'break' not in code_no_comments and 'return' not in code_no_comments and 'raise' not in code_no_comments:
                warnings.append("Unbounded loop: while True found without a clear exit condition (break/return/raise)")

            # 7. Python specific silent failures
            if re.search(r'\bexcept[^:]*:\s*(?:pass|#\s*.*)\s*(?:\n|$)', code_no_comments):
                warnings.append("Silent failure (Python): except block contains only pass or is empty")


            # 8. Insecure deserialization
            if re.search(r'\b(pickle\.load|pickle\.loads|yaml\.load)\b\s*\(', code_no_comments):
                if 'SafeLoader' not in code_no_comments:
                    warnings.append("Security risk: insecure deserialization (pickle or unsafe yaml.load) detected")

            # 9. Path traversal risk
            if re.search(r'\bopen\s*\(\s*[^,)]*([f"]|\+).*[''"]', code_no_comments):
                warnings.append("Security risk: potential path traversal (unvalidated string concatenation in open())")

            # 10. Insecure file permissions
            if re.search(r'\bos\.chmod\s*\(.*?(?:0o777|777|0777)\b', code_no_comments):
                warnings.append("Security risk: insecure file permissions (chmod 777) detected")

            # 11. Async safety: blocking calls in async functions
            if 'async def' in code_no_comments:
                blocking_calls = {
                    'time.sleep': 'await asyncio.sleep()',
                    'requests.': 'httpx or aiohttp',
                    'subprocess.': 'asyncio.create_subprocess_exec()',
                    'shutil.': 'executor or async alternative',
                }
                for call, alt in blocking_calls.items():
                    if call in code_no_comments:
                        warnings.append(f"Async safety: blocking call '{call}' detected in async function. Use {alt} instead.")

            # 12. Memory safety: unbounded collections in loops
            # Heuristic: looking for while/for loops that append to something without a size check/clear
            if re.search(r'\b(while|for)\b.*?\n(\s+).*?\.(append|add|update|extend)\(', code_no_comments, re.DOTALL):
                if 'len(' not in code_no_comments and 'clear()' not in code_no_comments and 'pop(' not in code_no_comments:
                    warnings.append("Memory safety: potential unbounded collection growth in loop (no len check or clear)")

            # 13. Concurrency safety: global state
            if re.search(r'\bglobal\s+\w+', code_no_comments):
                warnings.append("Concurrency risk: use of 'global' keyword detected; ensure thread-safety with locks")

            # 14. LRU Cache without maxsize
            if '@lru_cache' in code_no_comments and 'maxsize=' not in code_no_comments:
                warnings.append("Memory safety: @lru_cache used without explicit maxsize (defaults to 128, but explicit is better)")
        # 1. Naming Pattern (Verb-Noun)
        if symbol_kind not in ("Class", "Interface", "Enum", "Variable", "Module"):
            verbs = {"get", "set", "calculate", "validate", "fetch", "parse", "process", 
                     "run", "check", "update", "delete", "create", "load", "save", 
                     "handle", "start", "stop", "is", "has", "should", "can", "extract", "write", "read"}
            # Split camelCase or snake_case
            words = re.sub('([A-Z])', r' \1', name).replace('_', ' ').lower().split()
            if words and words[0] not in verbs:
                warnings.append(f"Function naming does not follow verb-noun pattern (e.g. fetchMarketData). Got: {name}")

        clean_code = ""
        if code:
            lines = code.splitlines()
            # 2. Length check
            if len(lines) > 50:
                warnings.append("Function is too long (> 50 lines)")

            # 3. Nesting check
            for idx, line in enumerate(lines):
                indent = len(line) - len(line.lstrip())
                # 16 spaces (4 levels of 4-space indent) or 4 tabs
                if indent >= 16 or line.count('\t') >= 4:
                    warnings.append(f"Deep nesting detected (> 3 levels) around line {idx + 1}")
                    break

            # Helper to clean code from comments and strings for accurate regex matching
            # Replace block comments
            clean_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
            clean_code = re.sub(r'"""\s*.*?\s*"""', '', clean_code, flags=re.DOTALL)
            clean_code = re.sub(r"'''\s*.*?\s*'''", '', clean_code, flags=re.DOTALL)
            # Replace single line comments
            clean_code = re.sub(r'//.*', '', clean_code)
            clean_code = re.sub(r'#.*', '', clean_code)
            # Replace string literals
            clean_code = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', clean_code)
            clean_code = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", clean_code)
            clean_code = re.sub(r'`[^`\\]*(?:\\.[`\\]*)*`', '``', clean_code)

            clean_lines = clean_code.splitlines()

            # --- 1. Short/vague variable name check ---
            for line in clean_lines:
                if re.search(r'\b(let|const|var)\s+([a-zA-Z])\b', line) or re.search(r'\b([a-zA-Z])\s*=[^=]', line):
                    warnings.append("Short/vague variable name detected")
                    break

            # --- 2. Immutability violations ---
            if any(re.search(r'\.(push|pop|splice|shift|unshift)\(', line) for line in clean_lines):
                warnings.append("Immutability violation: mutation methods used")

            # --- 3. Missing try/catch on I/O ---
            has_io = any(re.search(r'\b(fetch|open)\b', line) for line in clean_lines)
            has_try = any(re.search(r'\b(try|except|catch)\b', line) for line in clean_lines)
            if has_io and not has_try:
                warnings.append("Missing try/catch block on I/O operations")

            # --- 4. Magic numbers check ---
            magic_number_found = False
            for line in clean_lines:
                for num_str in re.findall(r'(?<!\w)-?\d+(?:\.\d+)?\b', line):
                    try:
                        val = float(num_str)
                        if val not in {-1.0, 0.0, 1.0, 100.0}:
                            warnings.append(f"Magic number detected: {num_str}")
                            magic_number_found = True
                            break
                    except ValueError:
                        pass
                if magic_number_found:
                    break

            # --- 6. Ternary hell check ---
            for line in clean_lines:
                if line.count('?') >= 2 and line.count(':') >= 2:
                    warnings.append("Ternary hell detected: multiple operators on the same line")
                    break

            # --- 7. Stating the obvious comment check ---
            orig_lines = code.splitlines()
            for idx, line in enumerate(orig_lines[:-1]):
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('//'):
                    comment_text = stripped.lstrip('/#* \t').lower()
                    if any(kw in comment_text for kw in ("increment", "get", "getter", "return", "obvious")):
                        next_line = ""
                        for next_idx in range(idx + 1, len(orig_lines)):
                            if orig_lines[next_idx].strip():
                                next_line = orig_lines[next_idx].strip()
                                break
                        if next_line:
                            is_increment = '++' in next_line or '+=' in next_line or re.search(r'=\s*.*\+\s*1\b', next_line)
                            is_getter = 'return' in next_line or next_line.startswith('get') or next_line.startswith('def get_')
                            if is_increment or is_getter:
                                warnings.append("Stating the obvious comment detected")
                                break

            # --- 8. Sequential awaits check ---
            non_empty_clean_lines = [line for line in clean_lines if line.strip()]
            for idx in range(len(non_empty_clean_lines) - 1):
                if 'await' in non_empty_clean_lines[idx] and 'await' in non_empty_clean_lines[idx + 1]:
                    warnings.append("Sequential awaits detected: run them in parallel if possible")
                    break

        # --- 5. Boolean parameter flags ---
        combined_text = f"{signature}\n{clean_code}"
        if re.search(r'\b(is_[a-zA-Z0-9_]+|has_[a-zA-Z0-9_]+|enable|disable|active)\s*:\s*(bool|boolean)\b', combined_text, re.IGNORECASE) or \
           re.search(r'\b(is_[a-zA-Z0-9_]+|has_[a-zA-Z0-9_]+|enable|disable|active)\s*=\s*(True|False|true|false)\b', combined_text):
            warnings.append("Boolean parameter flag detected")

        return warnings

    def parse(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a raw function record from the MCP graph into a DocstringGenome.

        The record should have at minimum: name, file, docstring.
        Optional fields: language (overrides file-extension detection), signature.
        """
        name = record.get("name", "unknown")
        file_path = record.get("file", "")
        docstring = record.get("docstring") or ""
        signature = record.get("signature") or ""
        code_snippet = record.get("code_snippet") or ""

        # Language detection: explicit field wins
        language = record.get("language") or detect_language(file_path)

        params = extract_params(docstring, language)
        returns = extract_returns(docstring, language)
        rules = extract_business_rules(docstring, language)

        warnings = []
        warnings.extend(self.parse_coding_standards(record))
        if not docstring or not docstring.strip():
            warnings.append("Missing docstring")
        else:
            # Check if signature has params but parsed params is empty
            if "(" in signature and ")" in signature:
                sig_content = signature.split("(", 1)[1].rsplit(")", 1)[0]
                sig_params = [p.strip() for p in sig_content.split(",") if p.strip()]
                # If there are params in signature but none parsed in docstring (for languages supporting params)
                if sig_params and not params and language.lower() in ("python", "javascript", "typescript", "solidity", "rust", "cpp", "c"):
                    warnings.append("Malformed docstring: signature parameters are not documented")

        dataflow = extract_dataflow(code_snippet, language)
        
        # Extract variables from dataflow
        variables = []
        seen_vars = set()
        for flow in dataflow:
            v = flow.get("variable")
            if v and v not in seen_vars:
                variables.append(v)
                seen_vars.add(v)

        return {
            "name": name,
            "file": file_path,
            "business_rules": rules,
            "code_snippet": code_snippet,
            "signature": signature,
            "docstring": docstring,
            "language": language,
            "params": params,
            "returns": returns,
            "warnings": warnings,
            "dataflow": dataflow,
            "variables": variables,
        }
