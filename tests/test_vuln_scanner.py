import pytest
from typing import Dict, Any, List
from brain.vuln_scanner import VulnerabilityScanner

class MockIndexer:
    def __init__(self, functions: List[Dict[str, Any]], rules: List[Any]):
        self.functions = functions
        self.rules = rules

    def query_graph(self, query: str) -> List[Dict[str, Any]]:
        return []

def test_scan_missing_authorization():
    # Mock a critical function with NO authorization rule
    critical_funcs = [
        {
            "name": "delete_user_account",
            "file": "auth.py",
            "business_score": 0.85,
            "mass": 5.0,
            "isExported": True
        }
    ]
    # No rules for this function
    rules = []
    
    indexer = MockIndexer(critical_funcs, rules)
    scanner = VulnerabilityScanner(indexer)
    scanner.set_data(critical_funcs, [])
    
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
            "code_snippet": "def update_balance(amt): balance += amt", # Missing 'owner' check
            "isExported": True
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
    scanner.set_data(critical_funcs, rules)
    
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
    scanner.set_data(funcs, rules)
    
    vulns = scanner.scan_sensitive_exposure()
    
    assert len(vulns) == 1
    assert vulns[0]["cwe"] == "CWE-532"

def test_scan_missing_authorization_internal_skip():
    # Mock a critical function that is INTERNAL
    critical_funcs = [
        {
            "name": "calibrate_physics",
            "file": "engine.py",
            "business_score": 0.9,
            "mass": 10.0,
            "isExported": False
        }
    ]
    rules = []
    
    indexer = MockIndexer(critical_funcs, rules)
    scanner = VulnerabilityScanner(indexer)
    scanner.set_data(critical_funcs, [])
    
    vulns = scanner.scan_missing_authorization()
    
    # Should be empty because it matches an internal pattern ('calibrate')
    assert len(vulns) == 0

def test_scan_missing_authorization_api_marker():
    # Mock a critical function with a FastAPI decorator
    critical_funcs = [
        {
            "name": "create_order",
            "file": "api.py",
            "business_score": 0.8,
            "code_snippet": "@app.post('/orders')\ndef create_order(): pass"
        }
    ]
    
    indexer = MockIndexer(critical_funcs, [])
    scanner = VulnerabilityScanner(indexer)
    scanner.set_data(critical_funcs, [])
    
    vulns = scanner.scan_missing_authorization()
    
    assert len(vulns) == 1
    assert vulns[0]["function"] == "create_order"
