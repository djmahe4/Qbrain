import re
from typing import List, Dict, Any

class VulnerabilityScanner:
    def __init__(self, indexer):
        self.indexer = indexer

    def scan_missing_authorization(self) -> List[Dict[str, Any]]:
        """CWE-862: Missing Authorization for critical functions."""
        # Find critical functions (high business score)
        query = "MATCH (f:Function) WHERE f.business_score > 0.65 RETURN f"
        critical_funcs = self.indexer.query_graph(query)
        
        vulnerabilities = []
        for func in critical_funcs:
            fname = func["name"]
            # Check if it has an authorization rule
            rule_query = f"MATCH (f:Function {{name: '{fname}'}})-[:IMPLEMENTS]->(br:BusinessRule {{category: 'authorization'}}) RETURN br"
            auth_rules = self.indexer.query_graph(rule_query)
            
            if not auth_rules:
                vulnerabilities.append({
                    "cwe": "CWE-862",
                    "title": "Missing Authorization",
                    "function": fname,
                    "file": func.get("file", "unknown"),
                    "severity": "CRITICAL" if func.get("business_score", 0) > 0.8 else "HIGH",
                    "description": f"Function '{fname}' has a high business relevance ({func.get('business_score'):.2f}) but no detected authorization checks."
                })
        return vulnerabilities

    def scan_incorrect_authorization(self) -> List[Dict[str, Any]]:
        """CWE-863: Incorrect Authorization / CWE-639: IDOR."""
        query = "MATCH (f:Function)-[:IMPLEMENTS]->(br:BusinessRule {category: 'authorization'}) RETURN f, br"
        pairs = self.indexer.query_graph(query)
        
        vulnerabilities = []
        for pair in pairs:
            # Handle different query result formats from Neo4j mocks vs real
            func = pair.get("f") or pair
            rule = pair.get("br") or pair
            
            fname = func.get("name")
            code = func.get("code_snippet") or ""
            rule_desc = rule.get("description", "").lower()
            
            # Simple heuristic: if rule mentions 'owner' or 'user' but code doesn't have checks
            if any(kw in rule_desc for kw in ["owner", "sender", "user_id", "caller"]):
                check_keywords = ["==", "!=", "if", "assert", "require", "throw", "raise"]
                if not any(kw in code.lower() for kw in check_keywords):
                    vulnerabilities.append({
                        "cwe": "CWE-863",
                        "title": "Incorrect Authorization (Potential Bypass)",
                        "function": fname,
                        "file": func.get("file", "unknown"),
                        "severity": "HIGH",
                        "description": f"Function '{fname}' claims to implement authorization ('{rule.get('description')}'), but the code snippet lacks obvious comparison or requirement checks."
                    })
        return vulnerabilities

    def scan_sensitive_exposure(self) -> List[Dict[str, Any]]:
        """CWE-200: Exposure of Sensitive Information / CWE-532: Insertion into Logs."""
        query = "MATCH (f:Function)-[:IMPLEMENTS]->(br:BusinessRule) WHERE br.category IN ['event', 'io'] RETURN f, br"
        pairs = self.indexer.query_graph(query)
        
        vulnerabilities = []
        sensitive_kws = ["password", "secret", "token", "api_key", "credential", "private_key"]
        
        for pair in pairs:
            func = pair.get("f") or pair
            rule = pair.get("br") or pair
            
            fname = func.get("name").lower()
            doc = func.get("docstring", "").lower()
            
            if any(kw in fname or kw in doc for kw in sensitive_kws):
                # Check if there's a sanitization rule
                sanitization_kws = ["mask", "sanitize", "hash", "strip", "redact"]
                rule_desc = rule.get("description", "").lower()
                if not any(kw in rule_desc for kw in sanitization_kws):
                    vulnerabilities.append({
                        "cwe": "CWE-532",
                        "title": "Sensitive Information Exposure",
                        "function": func["name"],
                        "file": func.get("file", "unknown"),
                        "severity": "MEDIUM",
                        "description": f"Function '{func['name']}' handles sensitive data (keywords: {[kw for kw in sensitive_kws if kw in fname or kw in doc]}) in an I/O or Event context, but no sanitization/masking rule was found."
                    })
        return vulnerabilities

    def run_all_scans(self) -> List[Dict[str, Any]]:
        all_vulns = []
        all_vulns.extend(self.scan_missing_authorization())
        all_vulns.extend(self.scan_incorrect_authorization())
        all_vulns.extend(self.scan_sensitive_exposure())
        return all_vulns
