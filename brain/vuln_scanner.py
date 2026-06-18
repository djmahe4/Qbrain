import re
from typing import List, Dict, Any, Optional

# Maps dangerous sink substrings → (CWE, short description)
# Used by scan_taint_to_sink() to classify dataflow findings
CWE_SINK_MAP: Dict[str, tuple] = {
    # PHP sinks (matched against DataFlowEngine flow_path["sink"])
    "echo":              ("CWE-79",  "XSS — Tainted variable rendered via echo"),
    "print":             ("CWE-79",  "XSS — Tainted variable rendered via print"),
    "innerHTML":         ("CWE-79",  "XSS — Tainted variable written to innerHTML"),
    "document.write":    ("CWE-79",  "XSS — Tainted variable passed to document.write"),
    "query":             ("CWE-89",  "SQL Injection — Tainted variable in DB query"),
    "mysqli_query":      ("CWE-89",  "SQL Injection — Tainted variable in mysqli_query"),
    "execute":           ("CWE-89",  "SQL Injection — Tainted variable in DB execute"),
    "exec":              ("CWE-78",  "OS Command Injection — Tainted variable in exec()"),
    "system":            ("CWE-78",  "OS Command Injection — Tainted variable in system()"),
    "shell_exec":        ("CWE-78",  "OS Command Injection — Tainted variable in shell_exec()"),
    "passthru":          ("CWE-78",  "OS Command Injection — Tainted variable in passthru()"),
    "popen":             ("CWE-78",  "OS Command Injection — Tainted variable in popen()"),
    "subprocess":        ("CWE-78",  "OS Command Injection — Tainted variable in subprocess"),
    "eval":              ("CWE-94",  "Code Injection — Tainted variable in eval()"),
    "create_function":   ("CWE-94",  "Code Injection — Tainted variable in create_function()"),
    "include":           ("CWE-98",  "Remote File Inclusion — Tainted include path"),
    "require":           ("CWE-98",  "Remote File Inclusion — Tainted require path"),
    "fopen":             ("CWE-22",  "Path Traversal — Tainted variable in fopen()"),
    "file_get_contents": ("CWE-918", "SSRF — Tainted URL in file_get_contents()"),
    "open":              ("CWE-22",  "Path Traversal — Tainted variable in open()"),
    "header":            ("CWE-601", "Open Redirect — Tainted value in HTTP header"),
    "setcookie":         ("CWE-614", "Sensitive Cookie — Tainted value in setcookie()"),
    "log":               ("CWE-532", "Sensitive Info in Logs — Tainted variable written to log"),
    "error_log":         ("CWE-532", "Sensitive Info in Logs — Tainted variable in error_log()"),
}

# Maps language_parser warning substrings → (CWE, severity)
WARNINGS_TO_CWE: Dict[str, tuple] = {
    "sql injection risk":               ("CWE-89",  "HIGH"),
    "hardcoded credentials":            ("CWE-798", "CRITICAL"),
    "insecure deserialization":         ("CWE-502", "HIGH"),
    "potential path traversal":         ("CWE-22",  "HIGH"),
    "use of eval":                      ("CWE-94",  "CRITICAL"),
    "security critical: use of eval":   ("CWE-94",  "CRITICAL"),
    "aliasing risky functions":         ("CWE-94",  "HIGH"),
    "debug=true":                       ("CWE-1188","MEDIUM"),
    "insecure file permissions":        ("CWE-276", "MEDIUM"),
    "unbounded loop":                   ("CWE-400", "MEDIUM"),
    "memory safety: potential unbounded":("CWE-400","MEDIUM"),
    "concurrency risk":                 ("CWE-362", "MEDIUM"),
    "insecure default":                 ("CWE-1188","MEDIUM"),
    "blocking call":                    ("CWE-400", "LOW"),
}


class VulnerabilityScanner:
    def __init__(self, indexer):
        self.indexer = indexer
        self.functions: List[Dict[str, Any]] = []
        self.rules: List[Any] = []  # Can be BusinessRule objects or dicts

    def set_data(self, functions: List[Dict[str, Any]], rules: List[Any]):
        """Inject in-memory data for scanning."""
        self.functions = functions
        self.rules = rules

    # -------------------------------------------------------------------------
    # CWE-862: Missing Authorization
    # -------------------------------------------------------------------------
    def scan_missing_authorization(self) -> List[Dict[str, Any]]:
        """CWE-862: Missing Authorization for critical functions."""
        vulnerabilities = []
        internal_patterns = [r"^test_", r"^mock_", r"_test$", r"internal_", r"^calibrate", r"sync_library"]
        api_entrypoint_markers = [
            r"@app\.(get|post|put|delete|patch|route)",
            r"@router\.",
            r"@authorized", r"@requires", r"@protected",
            r"handler", r"controller", r"endpoint", r"api"
        ]

        for func in self.functions:
            fname = func["name"]
            file_path = func.get("file", "unknown").lower()
            if "test" in file_path or any(re.search(p, fname, re.IGNORECASE) for p in internal_patterns):
                continue

            score = func.get("business_score", 0)
            if score <= 0.4:
                if not (func.get("mass", 0) > 1.2 or func.get("isExported")):
                    continue

            has_auth = any(
                (getattr(r, "source_function", "") == fname or r.get("source_function") == fname) and
                (getattr(r, "category", "") == "authorization" or r.get("category") == "authorization")
                for r in self.rules
            )

            if not has_auth:
                code = func.get("code_snippet", "")
                doc = func.get("docstring", "").lower()
                is_likely_api = any(re.search(p, code) for p in api_entrypoint_markers) or \
                                any(kw in doc for kw in ["api", "endpoint", "handler", "request", "public"]) or \
                                func.get("isExported", False)

                if is_likely_api:
                    vulnerabilities.append({
                        "cwe": "CWE-862",
                        "title": "Missing Authorization",
                        "function": fname,
                        "file": func.get("file", "unknown"),
                        "severity": "CRITICAL" if score > 0.8 else "HIGH",
                        "description": f"Function '{fname}' is likely a public API/entrypoint but has no detected authorization checks."
                    })
        return vulnerabilities

    # -------------------------------------------------------------------------
    # CWE-863: Incorrect Authorization / CWE-639: IDOR
    # -------------------------------------------------------------------------
    def scan_incorrect_authorization(self) -> List[Dict[str, Any]]:
        """CWE-863: Incorrect Authorization / CWE-639: IDOR."""
        vulnerabilities = []
        auth_pairs = []
        for rule in self.rules:
            cat = getattr(rule, "category", "") or rule.get("category", "")
            if cat == "authorization":
                fname = getattr(rule, "source_function", "") or rule.get("source_function")
                func = next((f for f in self.functions if f["name"] == fname), None)
                if func:
                    auth_pairs.append((func, rule))

        for func, rule in auth_pairs:
            fname = func.get("name")
            code = func.get("code_snippet") or ""
            rule_desc = (getattr(rule, "description", "") or rule.get("description", "")).lower()
            if any(kw in rule_desc for kw in ["owner", "sender", "user_id", "caller"]):
                check_keywords = ["==", "!=", "if ", "assert", "require", "throw", "raise"]
                if not any(kw in code.lower() for kw in check_keywords):
                    vulnerabilities.append({
                        "cwe": "CWE-863",
                        "title": "Incorrect Authorization (Potential Bypass)",
                        "function": fname,
                        "file": func.get("file", "unknown"),
                        "severity": "HIGH",
                        "description": f"Function '{fname}' claims authorization ('{rule_desc[:100]}...') but lacks comparison/requirement checks in code."
                    })
        return vulnerabilities

    # -------------------------------------------------------------------------
    # CWE-200 / CWE-532: Sensitive Info Exposure
    # -------------------------------------------------------------------------
    def scan_sensitive_exposure(self) -> List[Dict[str, Any]]:
        """CWE-200: Sensitive Info Exposure / CWE-532: Insertion into Logs."""
        vulnerabilities = []
        sensitive_kws = ["password", "secret", "token", "api_key", "credential", "private_key"]
        log_sinks = re.compile(r'\b(print|log|logger\.|console\.log|error_log)\b', re.IGNORECASE)
        sanitization_kws = ["mask", "sanitize", "hash", "strip", "redact"]

        for func in self.functions:
            fname = func.get("name", "").lower()
            doc = func.get("docstring", "").lower()
            code = func.get("code_snippet", "") or ""

            # Check function name/doc heuristic (original)
            if any(kw in fname or kw in doc for kw in sensitive_kws):
                for rule in self.rules:
                    cat = getattr(rule, "category", "") or rule.get("category", "")
                    rfname = getattr(rule, "source_function", "") or rule.get("source_function", "")
                    if rfname != func.get("name") or cat not in ["event", "io"]:
                        continue
                    rule_desc = (getattr(rule, "description", "") or rule.get("description", "")).lower()
                    if not any(kw in rule_desc for kw in sanitization_kws):
                        vulnerabilities.append({
                            "cwe": "CWE-532",
                            "title": "Sensitive Information Exposure",
                            "function": func["name"],
                            "file": func.get("file", "unknown"),
                            "severity": "MEDIUM",
                            "description": f"Function '{func['name']}' handles sensitive data in I/O context without sanitization."
                        })

            # Also check code directly: sensitive vars flowing into log sinks
            if log_sinks.search(code):
                for kw in sensitive_kws:
                    if re.search(rf'\b{kw}\b', code, re.IGNORECASE):
                        if not any(san in code.lower() for san in sanitization_kws):
                            vulnerabilities.append({
                                "cwe": "CWE-532",
                                "title": "Sensitive Info in Logs",
                                "function": func["name"],
                                "file": func.get("file", "unknown"),
                                "severity": "MEDIUM",
                                "description": f"Function '{func['name']}' may log sensitive field '{kw}' without masking."
                            })
                            break

        return vulnerabilities

    # -------------------------------------------------------------------------
    # CWE-78/79/89/94/22/98/601/918/532: Taint-to-Sink Dataflow
    # -------------------------------------------------------------------------
    def scan_taint_to_sink(self) -> List[Dict[str, Any]]:
        """
        CWE-78/79/89/94/22/98/312/532/601/918:
        Detect tainted variables reaching dangerous sinks via DataFlowEngine flow_paths.
        Deduplicates findings on the same line/pos for the same variable/CWE.
        """
        findings = []
        seen = set()
        # Sort map by key length descending to match most specific sink first
        sorted_sinks = sorted(CWE_SINK_MAP.items(), key=lambda x: len(x[0]), reverse=True)
        
        for func in self.functions:
            for path in func.get("flow_paths", []):
                if path.get("state") != "TAINTED":
                    continue
                sink = (path.get("sink") or "").lower()
                line = path.get("line")
                var = path.get("variable")
                file_path = path.get("file_path") or func.get("file", "unknown")
                
                for sink_kw, (cwe, desc) in sorted_sinks:
                    if sink_kw in sink:
                        dedup_key = (file_path, line, var, cwe)
                        if dedup_key in seen:
                            break
                        seen.add(dedup_key)
                        
                        line_info = f" at line {line}" if line else ""
                        findings.append({
                            "cwe": cwe,
                            "title": desc,
                            "function": func["name"],
                            "file": file_path,
                            "severity": "CRITICAL",
                            "description": (
                                f"{desc}: variable '{var}' "
                                f"(source: {path.get('source', 'unknown')}) "
                                f"reaches sink '{sink}'{line_info}."
                            )
                        })
                        break  # Only report the highest-priority (most specific) CWE per path
        return findings

    # -------------------------------------------------------------------------
    # CWE-798: Hardcoded Credentials
    # -------------------------------------------------------------------------
    def scan_hardcoded_credentials(self) -> List[Dict[str, Any]]:
        """CWE-798: Use of Hard-coded Credentials in code snippets."""
        findings = []
        cred_pattern = re.compile(
            r'\b(password|secret|api_key|token|credential|auth_key|private_key)\b'
            r'\s*[:=]\s*["\'][^"\']{3,}["\']',
            re.IGNORECASE
        )
        for func in self.functions:
            code = func.get("code_snippet", "") or ""
            match = cred_pattern.search(code)
            if match:
                findings.append({
                    "cwe": "CWE-798",
                    "title": "Hardcoded Credentials",
                    "function": func["name"],
                    "file": func.get("file", "unknown"),
                    "severity": "CRITICAL",
                    "description": (
                        f"Function '{func['name']}' contains a hardcoded credential "
                        f"(matched: '{match.group(1)}')."
                    )
                })
        return findings

    # -------------------------------------------------------------------------
    # CWE-400: Uncontrolled Resource Consumption
    # -------------------------------------------------------------------------
    def scan_resource_consumption(self) -> List[Dict[str, Any]]:
        """CWE-400: Uncontrolled Resource Consumption (infinite loops, no timeout)."""
        findings = []
        for func in self.functions:
            code = func.get("code_snippet", "") or ""
            # Infinite loop without exit
            if re.search(r'\bwhile\s+True\b', code) and \
               not re.search(r'\bbreak\b|\breturn\b|\braise\b', code):
                findings.append({
                    "cwe": "CWE-400",
                    "title": "Uncontrolled Resource Consumption (Infinite Loop)",
                    "function": func["name"],
                    "file": func.get("file", "unknown"),
                    "severity": "HIGH",
                    "description": f"Function '{func['name']}' contains 'while True' without break/return/raise."
                })
            # HTTP request without timeout
            if "requests." in code and "timeout=" not in code:
                findings.append({
                    "cwe": "CWE-400",
                    "title": "HTTP Request Without Timeout",
                    "function": func["name"],
                    "file": func.get("file", "unknown"),
                    "severity": "MEDIUM",
                    "description": f"Function '{func['name']}' makes an HTTP request (requests.*) without a timeout."
                })
        return findings

    # -------------------------------------------------------------------------
    # CWE-312: Cleartext Storage of Sensitive Information
    # -------------------------------------------------------------------------
    def scan_cleartext_storage(self) -> List[Dict[str, Any]]:
        """CWE-312: Cleartext Storage of Sensitive Information."""
        findings = []
        sensitive = re.compile(r'\b(password|secret|token|credential|api_key)\b', re.IGNORECASE)
        storage_sinks = re.compile(
            r'\b(open\s*\(|write\s*\(|json\.dump|yaml\.dump|pickle\.dump|sqlite3|INSERT\s+INTO)\b',
            re.IGNORECASE
        )
        for func in self.functions:
            code = func.get("code_snippet", "") or ""
            if sensitive.search(code) and storage_sinks.search(code):
                if not re.search(r'\b(hash|bcrypt|sha|pbkdf2|encrypt|AES)\b', code, re.IGNORECASE):
                    findings.append({
                        "cwe": "CWE-312",
                        "title": "Cleartext Storage of Sensitive Information",
                        "function": func["name"],
                        "file": func.get("file", "unknown"),
                        "severity": "HIGH",
                        "description": (
                            f"Function '{func['name']}' appears to write sensitive data "
                            f"to storage without hashing or encryption."
                        )
                    })
        return findings

    # -------------------------------------------------------------------------
    # Wire language_parser warnings → CWE findings
    # -------------------------------------------------------------------------
    def scan_from_parser_warnings(self) -> List[Dict[str, Any]]:
        findings = []
        for func in self.functions:
            for warning in func.get("warnings", []):
                w_lower = warning.lower()
                for kw, (cwe, severity) in WARNINGS_TO_CWE.items():
                    if kw in w_lower:
                        findings.append({
                            "cwe": cwe,
                            "title": warning[:80],
                            "function": func["name"],
                            "file": func.get("file", "unknown"),
                            "severity": severity,
                            "description": warning
                        })
                        break
        return findings

    # -------------------------------------------------------------------------
    # Orchestrator
    # -------------------------------------------------------------------------
    def run_all_scans(self) -> List[Dict[str, Any]]:
        all_vulns = []
        all_vulns.extend(self.scan_missing_authorization())
        all_vulns.extend(self.scan_incorrect_authorization())
        all_vulns.extend(self.scan_sensitive_exposure())
        all_vulns.extend(self.scan_taint_to_sink())
        all_vulns.extend(self.scan_hardcoded_credentials())
        all_vulns.extend(self.scan_resource_consumption())
        all_vulns.extend(self.scan_cleartext_storage())
        all_vulns.extend(self.scan_from_parser_warnings())
        return all_vulns
