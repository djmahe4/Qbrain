import pytest
from typing import Dict, Any, List
from brain.vuln_scanner import VulnerabilityScanner

class MockIndexer:
    def __init__(self, functions: List[Dict[str, Any]], rules: List[Dict[str, Any]]):
        self.functions = functions
        self.rules = rules

    def query_graph(self, query: str) -> List[Dict[str, Any]]:
        if "MATCH (f:Function)" in query and "WHERE f.business_score >" in query:
            return self.functions
        if "IMPLEMENTS" in query and "authorization" in query:
            return [{"f": f, "br": r} for f in self.functions for r in self.rules if r["source_function"] == f["name"] and r["category"] == "authorization"]
        if "IMPLEMENTS" in query and "['event', 'io']" in query:
            return [{"f": f, "br": r} for f in self.functions for r in self.rules if r["source_function"] == f["name"] and r["category"] in ["event", "io"]]
        if "MATCH (f:Function {name:" in query and "[:IMPLEMENTS]->(br:BusinessRule)" in query:
            import re
            m = re.search(r"f\.name = '([^']+)'", query)
            if m:
                fname = m.group(1)
                return [r for r in self.rules if r["source_function"] == fname]
        return []

def test_scan_missing_authorization():
    # Mock a critical function with NO authorization rule
    critical_funcs = [
        {
            "name": "delete_user_account",
            "file": "auth.py",
            "business_score": 0.85,
            "mass": 5.0
        }
    ]
    # No rules for this function
    rules = []
    
    indexer = MockIndexer(critical_funcs, rules)
    scanner = VulnerabilityScanner(indexer)
    
    vulns = scanner.scan_missing_authorization()
    
    assert len(vulns) == 1
    assert vulns[0]["cwe"] == "CWE-862"
    assert vulns[0]["function"] == "delete_user_account"

def test_scan_incorrect_authorization():
    # Mock a function WITH an authorization rule but NO code check
    critical_funcs = [
        {
            "name": "update_balance",
            "file": "bank.py",
            "business_score": 0.9,
            "code_snippet": "def update_balance(amt): balance += amt" # Missing 'owner' check
        }
    ]
    rules = [
        {
            "source_function": "update_balance",
            "category": "authorization",
            "description": "Only the account owner can update balance"
        }
    ]
    
    indexer = MockIndexer(critical_funcs, rules)
    scanner = VulnerabilityScanner(indexer)
    
    vulns = scanner.scan_incorrect_authorization()
    
    assert len(vulns) == 1
    assert vulns[0]["cwe"] == "CWE-863"

def test_scan_sensitive_exposure():
    # Mock an event function that logs a password
    funcs = [
        {
            "name": "log_login_attempt",
            "file": "logger.py",
            "docstring": "Logs the login attempt with password",
            "business_score": 0.3
        }
    ]
    # 'event' category will be identified by the scanner
    rules = [
        {
            "source_function": "log_login_attempt",
            "category": "event",
            "description": "Logs the login attempt"
        }
    ]
    
    indexer = MockIndexer(funcs, rules)
    scanner = VulnerabilityScanner(indexer)
    
    vulns = scanner.scan_sensitive_exposure()
    
    assert len(vulns) == 1
    assert vulns[0]["cwe"] == "CWE-532"
