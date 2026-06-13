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
}



def detect_language(file_path: str) -> str:
    """Return language identifier from file extension, or 'generic' if unknown."""
    if not file_path:
        return "generic"
    for ext, lang in _EXTENSION_MAP.items():
        if file_path.endswith(ext):
            return lang
    return "generic"


# ─────────────────────────── Python (Google/NumPy/Sphinx) ───────────────────────────

_PY_PARAM_LINE_RE = re.compile(
    r"^\s+(\w+)\s*(?:\(([^)]*)\))?\s*:\s*(.+)$"
)


def _parse_python_docstring(docstring: str) -> Dict[str, List[str]]:
    """Split a Python docstring into named sections using a simple state machine."""
    lines = docstring.splitlines()
    sections: Dict[str, List[str]] = {}
    current_section = None
    section_lines: List[str] = []

    HEADERS = {
        "args": "args",
        "arg": "args",
        "parameters": "args",
        "parameter": "args",
        "returns": "returns",
        "return": "returns",
        "yields": "returns",
        "yield": "returns",
    }
    TERMINATORS = {"raises", "raise", "note", "example", "see also"}

    for line in lines:
        stripped = line.strip()
        header_match = re.match(r"^([A-Za-z][A-Za-z0-9_ ]+):\s*$", stripped)
        if header_match:
            header_name = header_match.group(1).lower().strip()
            if header_name in HEADERS or header_name in TERMINATORS:
                if current_section:
                    sections[current_section] = section_lines
                current_section = HEADERS.get(header_name, header_name)
                section_lines = []
                continue

        if current_section:
            section_lines.append(line)

    if current_section:
        sections[current_section] = section_lines

    return sections


def _extract_params_python(docstring: str) -> List[Dict[str, str]]:
    sections = _parse_python_docstring(docstring)
    args_lines = sections.get("args", [])
    params: List[Dict[str, str]] = []

    current_param: Optional[Dict[str, str]] = None
    for line in args_lines:
        m = _PY_PARAM_LINE_RE.match(line)
        if m:
            if current_param:
                params.append(current_param)
            current_param = {
                "name": m.group(1),
                "type": (m.group(2) or "").strip(),
                "description": m.group(3).strip()
            }
        elif current_param and line.strip():
            if line.startswith(" "):
                current_param["description"] += " " + line.strip()

    if current_param:
        params.append(current_param)

    return params


def _extract_returns_python(docstring: str) -> Dict[str, str]:
    sections = _parse_python_docstring(docstring)
    returns_lines = sections.get("returns", [])
    if not returns_lines:
        return {"type": "", "description": ""}

    cleaned_lines = [l.strip() for l in returns_lines if l.strip()]
    if not cleaned_lines:
        return {"type": "", "description": ""}

    first_line = cleaned_lines[0]
    m = re.match(r"^([A-Za-z][\w\[\], .]*):\s*(.+)$", first_line)
    if m:
        ret_type = m.group(1).strip()
        ret_desc = m.group(2).strip()
        if len(cleaned_lines) > 1:
            ret_desc += " " + " ".join(cleaned_lines[1:])
        return {"type": ret_type, "description": ret_desc}

    return {"type": "", "description": " ".join(cleaned_lines)}



# ─────────────────────────── JSDoc (JS / TS) ───────────────────────────

_JSDOC_PARAM_RE = re.compile(
    r"@param\s*(?:\{([^}]*)\})?\s*(\w+)\s*(?:-\s*)?(.+)?",
    re.IGNORECASE
)
_JSDOC_RETURNS_RE = re.compile(
    r"@returns?\s*(?:\{([^}]*)\})?\s*(.+)?",
    re.IGNORECASE
)


def _extract_params_jsdoc(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    for m in _JSDOC_PARAM_RE.finditer(docstring):
        params.append({
            "name": m.group(2).strip(),
            "type": (m.group(1) or "").strip(),
            "description": (m.group(3) or "").strip()
        })
    return params


def _extract_returns_jsdoc(docstring: str) -> Dict[str, str]:
    m = _JSDOC_RETURNS_RE.search(docstring)
    if m:
        return {
            "type": (m.group(1) or "").strip(),
            "description": (m.group(2) or "").strip()
        }
    return {"type": "", "description": ""}


# ─────────────────────────── Solidity NatSpec ───────────────────────────

_NATSPEC_NOTICE_RE = re.compile(r"@notice\s+(.+)", re.IGNORECASE)
_NATSPEC_DEV_RE = re.compile(r"@dev\s+(.+)", re.IGNORECASE)
_NATSPEC_PARAM_RE = re.compile(r"@param\s+(\w+)\s+(.*)", re.IGNORECASE)
_NATSPEC_RETURN_RE = re.compile(r"@return\s+(?:(\w+)\s+)?(.*)", re.IGNORECASE)


def _extract_params_natspec(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    for m in _NATSPEC_PARAM_RE.finditer(docstring):
        params.append({"name": m.group(1).strip(), "type": "", "description": m.group(2).strip()})
    return params


def _extract_returns_natspec(docstring: str) -> Dict[str, str]:
    m = _NATSPEC_RETURN_RE.search(docstring)
    if m:
        name_or_desc = m.group(1) or ""
        desc = m.group(2) or ""
        full_desc = f"{name_or_desc} {desc}".strip()
        return {"type": "", "description": full_desc}
    return {"type": "", "description": ""}


def _extract_business_rules_natspec(docstring: str) -> List[str]:
    rules: List[str] = []
    for m in _NATSPEC_NOTICE_RE.finditer(docstring):
        rules.append(m.group(1).strip())
    for m in _NATSPEC_DEV_RE.finditer(docstring):
        rules.append(m.group(1).strip())
    return rules


# ─────────────────────────── Go ───────────────────────────

_GO_COMMENT_RE = re.compile(r"^//\s*(.+)$", re.MULTILINE)


def _extract_business_rules_go(docstring: str) -> List[str]:
    """Extract meaningful lines from Go comment blocks (// ...)."""
    lines = [m.group(1).strip() for m in _GO_COMMENT_RE.finditer(docstring)]
    # Filter out blank/trivial lines
    return [l for l in lines if len(l) > 5]


# ─────────────────────────── Rust ───────────────────────────

_RUST_LINE_RE = re.compile(r"^///?!?\s*(.*)$", re.MULTILINE)
_RUST_ARGS_BLOCK_RE = re.compile(r"#\s*Arguments\s*\n((?:.|\n)*?)(?=#\s|\Z)", re.IGNORECASE)
_RUST_ARG_ITEM_RE = re.compile(r"\*\s+`(\w+)`\s+-\s+(.*)")
_RUST_RETURNS_BLOCK_RE = re.compile(r"#\s*Returns\s*\n((?:.|\n)*?)(?=#\s|\Z)", re.IGNORECASE)


def _extract_params_rust(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    block_m = _RUST_ARGS_BLOCK_RE.search(docstring)
    if not block_m:
        return params
    for m in _RUST_ARG_ITEM_RE.finditer(block_m.group(1)):
        params.append({"name": m.group(1), "type": "", "description": m.group(2).strip()})
    return params


def _extract_returns_rust(docstring: str) -> Dict[str, str]:
    block_m = _RUST_RETURNS_BLOCK_RE.search(docstring)
    if not block_m:
        return {"type": "", "description": ""}
    desc = block_m.group(1).strip().lstrip("* ").strip()
    return {"type": "", "description": desc}


# ─────────────────────────── C/C++ (Doxygen) ───────────────────────────

_CPP_PARAM_RE = re.compile(r"(?:@|\\)param(?:\s*\[[^\]]*\])?\s+(\w+)\s+(.*)", re.IGNORECASE)
_CPP_RETURNS_RE = re.compile(r"(?:@|\\)returns?\s+(.*)", re.IGNORECASE)
_CPP_BRIEF_RE = re.compile(r"(?:@|\\)brief\s+(.*)", re.IGNORECASE)


def _extract_params_cpp(docstring: str) -> List[Dict[str, str]]:
    params: List[Dict[str, str]] = []
    for m in _CPP_PARAM_RE.finditer(docstring):
        params.append({
            "name": m.group(1).strip(),
            "type": "",
            "description": m.group(2).strip().rstrip("*/").strip()
        })
    return params


def _extract_returns_cpp(docstring: str) -> Dict[str, str]:
    m = _CPP_RETURNS_RE.search(docstring)
    if m:
        desc = m.group(1).splitlines()[0].rstrip("*/").strip()
        return {"type": "", "description": desc}
    return {"type": "", "description": ""}


def _extract_business_rules_cpp(docstring: str) -> List[str]:
    rules: List[str] = []
    for m in _CPP_BRIEF_RE.finditer(docstring):
        line = m.group(1).splitlines()[0].rstrip("*/").strip()
        if line:
            rules.append(line)

    KEYWORDS = {"only", "must", "should", "validates", "ensures", "requires", "checks",
                "verifies", "authorizes", "emits", "transfers", "mints", "burns"}
    sentences = re.split(r"[.!?]\s+", docstring.replace("\n", " "))
    for s in sentences:
        s = s.strip().lstrip("/*# ")
        clean_s = re.sub(r"(?:@|\\)[a-zA-Z]+", "", s).strip()
        words = set(clean_s.lower().split())
        if words & KEYWORDS:
            if clean_s not in rules:
                rules.append(clean_s)
    return rules


# ─────────────────────────── Public API ───────────────────────────

def extract_params(docstring: str, language: str) -> List[Dict[str, str]]:
    """Extract @param / Args sections from a docstring for the given language."""
    if not docstring:
        return []
    lang = language.lower()
    if lang == "python":
        return _extract_params_python(docstring)
    elif lang in ("javascript", "typescript"):
        return _extract_params_jsdoc(docstring)
    elif lang == "solidity":
        return _extract_params_natspec(docstring)
    elif lang == "rust":
        return _extract_params_rust(docstring)
    elif lang in ("cpp", "c"):
        return _extract_params_cpp(docstring)
    # go and generic — no structured params in comments
    return []


def extract_returns(docstring: str, language: str) -> Dict[str, str]:
    """Extract @return / Returns section from a docstring for the given language."""
    if not docstring:
        return {"type": "", "description": ""}
    lang = language.lower()
    if lang == "python":
        return _extract_returns_python(docstring)
    elif lang in ("javascript", "typescript"):
        return _extract_returns_jsdoc(docstring)
    elif lang == "solidity":
        return _extract_returns_natspec(docstring)
    elif lang == "rust":
        return _extract_returns_rust(docstring)
    elif lang in ("cpp", "c"):
        return _extract_returns_cpp(docstring)
    return {"type": "", "description": ""}


def extract_business_rules(docstring: str, language: str) -> List[str]:
    """
    Extract business rule strings from a docstring.
    For Solidity: @notice and @dev tags.
    For Go: meaningful comment lines.
    Others: generic sentence extraction from the docstring body.
    """
    if not docstring:
        return []
    lang = language.lower()
    if lang == "solidity":
        return _extract_business_rules_natspec(docstring)
    elif lang == "go":
        return _extract_business_rules_go(docstring)
    elif lang in ("cpp", "c"):
        return _extract_business_rules_cpp(docstring)
    # For Python/TS/JS/Rust: extract first meaningful sentences as rules
    # Simple heuristic: sentences containing business keywords
    KEYWORDS = {"only", "must", "should", "validates", "ensures", "requires", "checks",
                "verifies", "authorizes", "emits", "transfers", "mints", "burns"}
    sentences = re.split(r"[.!?]\s+", docstring.replace("\n", " "))
    rules: List[str] = []
    for s in sentences:
        s = s.strip().lstrip("/*# ")
        words = set(s.lower().split())
        if words & KEYWORDS:
            rules.append(s)
    return rules



def build_genome(genome_dict: Dict[str, Any]) -> str:
    """
    Build a single semantic genome string from a parsed DocstringGenome dict.
    Concatenates name, signature, docstring, and business rules for embedding.
    """
    name = genome_dict.get("name", "unknown")
    sig = genome_dict.get("signature") or ""
    doc = genome_dict.get("docstring") or ""
    rules = genome_dict.get("business_rules") or []

    parts = [name]
    if sig:
        parts.append(f"({sig})")
    if doc.strip():
        # Strip comment markers
        clean_doc = re.sub(r"[\*/]+", "", doc).strip()
        parts.append(f"— {clean_doc}")
    if rules:
        parts.append("Rules: " + "; ".join(rules))

    return " ".join(parts)


# ─────────────────────────── LanguageParser class ───────────────────────────

class LanguageParser:
    """
    Parses a raw MCP graph function record into a structured DocstringGenome dict.
    Supports Python, JS, TS, Solidity, Go, Rust, and generic fallback.
    """

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

        # Language detection: explicit field wins
        language = record.get("language") or detect_language(file_path)

        params = extract_params(docstring, language)
        returns = extract_returns(docstring, language)
        rules = extract_business_rules(docstring, language)

        return {
            "name": name,
            "file": file_path,
            "signature": signature,
            "docstring": docstring,
            "language": language,
            "params": params,
            "returns": returns,
            "business_rules": rules,
        }
