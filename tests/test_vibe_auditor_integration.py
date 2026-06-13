from brain.language_parser import LanguageParser

def test_vibe_auditor_security_checks():
    parser = LanguageParser()
    code = "eval('import os; os.system(\"rm -rf /\")')"
    warnings = parser.parse_coding_standards({"name": "unsafe", "code_snippet": code})
    assert any("security critical" in w.lower() for w in warnings)

def test_vibe_auditor_credential_checks():
    parser = LanguageParser()
    code = 'api_key = "12345-abcde"'
    warnings = parser.parse_coding_standards({"name": "config", "code_snippet": code})
    assert any("hardcoded credentials" in w.lower() for w in warnings)

def test_vibe_auditor_sql_injection_checks():
    parser = LanguageParser()
    code = 'db.execute(f"SELECT * FROM users WHERE id = {user_id}")'
    warnings = parser.parse_coding_standards({"name": "query", "code_snippet": code})
    assert any("sql injection" in w.lower() for w in warnings)

def test_vibe_auditor_production_risk_checks():
    parser = LanguageParser()
    code = 'requests.get("https://api.example.com")'
    warnings = parser.parse_coding_standards({"name": "fetch", "code_snippet": code})
    assert any("production risk" in w.lower() for w in warnings)

def test_vibe_auditor_unbounded_loop_checks():
    parser = LanguageParser()
    code = "while True:\n    print('looping')"
    warnings = parser.parse_coding_standards({"name": "loop", "code_snippet": code})
    assert any("unbounded loop" in w.lower() for w in warnings)

def test_vibe_auditor_silent_failure_checks():
    parser = LanguageParser()
    code = "try:\n    do_thing()\nexcept:\n    pass"
    warnings = parser.parse_coding_standards({"name": "silent", "code_snippet": code})
    assert any("silent failure" in w.lower() or "empty catch" in w.lower() for w in warnings)

def test_vibe_auditor_deserialization_checks():
    parser = LanguageParser()
    code = "data = pickle.load(f)"
    warnings = parser.parse_coding_standards({"name": "unsafe", "code_snippet": code})
    assert any("deserialization" in w.lower() for w in warnings)

def test_vibe_auditor_path_traversal_checks():
    parser = LanguageParser()
    code = 'open(f"data/{filename}.txt")'
    warnings = parser.parse_coding_standards({"name": "unsafe", "code_snippet": code})
    assert any("path traversal" in w.lower() for w in warnings)

def test_vibe_auditor_chmod_checks():
    parser = LanguageParser()
    code = "os.chmod('secret.txt', 0o777)"
    warnings = parser.parse_coding_standards({"name": "unsafe", "code_snippet": code})
    assert any("file permissions" in w.lower() for w in warnings)
