import re
from typing import List, Dict, Any, Optional

class VulnerabilityScanner:
    def __init__(self, indexer):
        self.indexer = indexer
        self.functions: List[Dict[str, Any]] = []
        self.rules: List[Any] = [] # Can be BusinessRule objects or dicts

    def set_data(self, functions: List[Dict[str, Any]], rules: List[Any]):
        """Inject in-memory data for scanning."""
        self.functions = functions
        self.rules = rules

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
            # More permissive for prototype repositories
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
                        "description": f"Function '{fname}' claims to implement authorization ('{rule_desc[:100]}...'), but the code snippet lacks obvious comparison or requirement checks."
                    })
        return vulnerabilities

    def scan_sensitive_exposure(self) -> List[Dict[str, Any]]:
        """CWE-200: Exposure of Sensitive Information / CWE-532: Insertion into Logs."""
        vulnerabilities = []
        sensitive_kws = ["password", "secret", "token", "api_key", "credential", "private_key"]
        target_pairs = []
        for rule in self.rules:
            cat = getattr(rule, "category", "") or rule.get("category", "")
            if cat in ["event", "io"]:
                fname = getattr(rule, "source_function", "") or rule.get("source_function")
                func = next((f for f in self.functions if f["name"] == fname), None)
                if func:
                    target_pairs.append((func, rule))

        for func, rule in target_pairs:
            fname = func.get("name").lower()
            doc = func.get("docstring", "").lower()
            if any(kw in fname or kw in doc for kw in sensitive_kws):
                sanitization_kws = ["mask", "sanitize", "hash", "strip", "redact"]
                rule_desc = (getattr(rule, "description", "") or rule.get("description", "")).lower()
                if not any(kw in rule_desc for kw in sanitization_kws):
                    vulnerabilities.append({
                        "cwe": "CWE-532",
                        "title": "Sensitive Information Exposure",
                        "function": func["name"],
                        "file": func.get("file", "unknown"),
                        "severity": "MEDIUM",
                        "description": f"Function '{func['name']}' handles sensitive data in an I/O or Event context, but no sanitization/masking rule was found."
                    })
        return vulnerabilities

    def run_all_scans(self) -> List[Dict[str, Any]]:
        all_vulns = []
        all_vulns.extend(self.scan_missing_authorization())
        all_vulns.extend(self.scan_incorrect_authorization())
        all_vulns.extend(self.scan_sensitive_exposure())
        return all_vulns
