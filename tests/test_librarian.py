import pytest
import os
import time
import json
from unittest.mock import MagicMock, patch
from brain.librarian import LibrarianEngine
import brain.cli

def test_librarian_creates_folders(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    assert os.path.exists(vault_path / "symbols")
    assert os.path.exists(vault_path / "files")
    assert os.path.exists(vault_path / "behaviors")
    assert os.path.exists(vault_path / "changes" / "recent")
    assert os.path.exists(vault_path / "changes" / "archive")
    assert os.path.exists(vault_path / "rules")
    assert os.path.exists(vault_path / "baseline.md")

def test_librarian_lock_mechanism(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))

    # Test lock acquire and release
    with engine.lock():
        lock_file = os.path.join(tmp_path, ".qbrain.lock")
        assert os.path.exists(lock_file)
        with open(lock_file, "r") as f:
            data = json.load(f)
            pid = data.get("pid")
            assert pid == os.getpid()

    assert not os.path.exists(lock_file)

def test_librarian_lock_collision(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))

    # Write a fake active lock file
    lock_file = os.path.join(tmp_path, ".qbrain.lock")
    with open(lock_file, "w") as f:
        f.write(str(os.getpid()))

    # Attempting to acquire lock should raise RuntimeError
    with pytest.raises(RuntimeError, match="locked"):
        with engine.lock():
            pass

def test_librarian_exports_symbols(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    file_data = {
        "file_path": "src/auth.cpp",
        "language": "cpp",
        "lines_of_code": 100,
        "size_bytes": 1024,
        "symbols_data": [{
            "name": "validateToken",
            "language": "cpp",
            "file": "src/auth.cpp",
            "signature": "bool validateToken(string t)",
            "docstring": "Validates a jwt token.",
            "params": [{"name": "t", "type": "string", "description": "token string"}],
            "returns": {"type": "bool", "description": "true if valid"},
            "business_rules": ["Validates expiry", "Checks signature"]
        }]
    }

    engine.export_file(file_data)
    file_doc = vault_path / "files" / "src_auth_cpp.md"
    assert os.path.exists(file_doc)
    with open(file_doc, "r", encoding="utf-8") as f:
        content = f.read()

    assert "type: file" in content
    assert "### Symbol: validateToken" in content
    assert "Validates a jwt token." in content


def test_librarian_exports_behavior_state_machine(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    behavior_data = {
        "name": "login-flow",
        "states": ["REQUEST_RECEIVED", "VALIDATING", "SUCCESS", "FAILURE"],
        "transitions": [
            {"from": "REQUEST_RECEIVED", "to": "VALIDATING"},
            {"from": "VALIDATING", "to": "SUCCESS", "condition": "valid_pass"},
            {"from": "VALIDATING", "to": "FAILURE", "condition": "invalid_pass"}
        ]
    }

    engine.export_behavior(behavior_data)
    behavior_file = vault_path / "behaviors" / "login-flow.md"
    assert os.path.exists(behavior_file)
    with open(behavior_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "type: behavior" in content
    assert "stateDiagram-v2" in content
    assert "VALIDATING --> SUCCESS" in content


def test_librarian_exports_warnings(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    warnings_list = [
        {"name": "badFunc", "file": "src/bad.py", "warnings": ["Missing docstring"]},
        {"name": "mismatchedFunc", "file": "src/mismatch.js", "warnings": ["Malformed docstring: signature parameters are not documented"]}
    ]

    engine.export_warnings(warnings_list)
    warnings_file = vault_path / "rules" / "warnings.md"
    assert os.path.exists(warnings_file)
    with open(warnings_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# Docstring & Quality Invariants Warnings" in content
    assert "badFunc\\|badFunc" in content
    assert "mismatchedFunc" in content
    assert "signature parameters are not documented" in content


@patch("brain.cli.get_engine")
def test_library_sync_code_snippet_warnings(mock_get_engine, tmp_path):
    from typer.testing import CliRunner
    from brain.cli import app
    from unittest.mock import patch

    vault_path = tmp_path / "obsidian_vault"
    mock_config = MagicMock()
    mock_config.repo_path = str(tmp_path)
    mock_config.data = {"vault_path": str(vault_path)}

    mock_indexer = MagicMock()
    mock_indexer.query_graph.return_value = [{
        "name": "tooLongFunction",
        "docstring": "This is a docstring.",
        "file": "src/utils.py",
        "line": 10,
        "complexity": 2.0,
        "sideEffects": 0.0,
        "isExported": True,
        "signature": "def tooLongFunction()",
        "language": "python"
    }]
    mock_indexer.get_code_snippet.return_value = {
        "code": "def tooLongFunction():\n" + "\n" * 55
    }

    mock_get_engine.return_value = (mock_config, mock_indexer, MagicMock(), MagicMock())

    runner = CliRunner()
    result = runner.invoke(app, ["library", "sync"])

    assert result.exit_code == 0
    warnings_file = vault_path / "rules" / "warnings.md"
    assert os.path.exists(warnings_file)
    with open(warnings_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# Docstring & Quality Invariants Warnings" in content
    assert "tooLongFunction" in content
    assert "Function is too long (> 50 lines)" in content


def test_librarian_exports_behavior_with_dataflow_and_variables(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    behavior_data = {
        "name": "test-dataflow-flow",
        "states": [
            "start",
            '[require] DVWA_WEB_PAGE_TO_ROOT . "vulnerabilities/javascript/source/{{$vulnerabilityFile}}"'
        ],
        "transitions": [
            {
                "from": "start",
                "to": '[require] DVWA_WEB_PAGE_TO_ROOT . "vulnerabilities/javascript/source/{{$vulnerabilityFile}}"'
            }
        ],
        "state_meta": {
            "start": {
                "variable_states": {
                    "$var1": {"state": "TAINTED", "type": "string", "constraints": ["not null"]}
                },
                "flow_paths": [
                    {"source": "$_GET", "sink": "echo", "variable": "$var1"}
                ]
            },
            '[require] DVWA_WEB_PAGE_TO_ROOT . "vulnerabilities/javascript/source/{{$vulnerabilityFile}}"': {
                "variable_states": {
                    "$var2": {"state": "SAFE", "type": "int", "constraints": []}
                },
                "flow_paths": []
            }
        }
    }

    engine.export_behavior(behavior_data)
    behavior_file = vault_path / "behaviors" / "test-dataflow-flow.md"
    assert os.path.exists(behavior_file)
    with open(behavior_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify state name double quotes are escaped or replaced
    assert "Parse error" not in content
    assert 'state "[require] DVWA_WEB_PAGE_TO_ROOT . "vulnerabilities' not in content
    assert "state \"Require: DVWA_WEB_PAGE_TO_ROOT . 'vulnerabilities/javascript/source/{{$vulnerabilityFile}}'\"" in content

    # Verify Dynamic Variable Tracking section is present
    assert "## Dynamic Variable Tracking" in content
    assert "| `$var1` | `GENERIC_TAINT` | `TAINTED` |" in content
    assert "| `$var2` | `GENERIC_TAINT` | `SAFE` |" in content

    # Verify Behavior Dataflow Tracking section is present
    assert "## Behavior Dataflow Tracking" in content
    assert "graph LR" in content
    assert '"$_GET"' in content
    assert '"echo"' in content


def test_behavioral_characteristics_export(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    behavior_data = {
        "name": "login-flow",
        "states": ["REQUEST_RECEIVED", "VALIDATING"],
        "transitions": [
            {"from": "REQUEST_RECEIVED", "to": "VALIDATING"}
        ],
        "state_meta": {
            "REQUEST_RECEIVED": {
                "file": "src/app.py",
                "line": 10,
                "kind": "Function",
                "code_snippet": "def receive_request(req):\n    try:\n        for item in req.items:\n            if item.val >= 100:\n                query = 'SELECT * FROM users WHERE id = ' + item.val\n                db.execute(query)\n    except Exception as e:\n        pass\n"
            },
            "VALIDATING": {
                "file": "src/app.py",
                "line": 20,
                "kind": "Function",
                "code_snippet": "def validate():\n    if timeout > 30:\n        raise TimeoutError()\n"
            }
        }
    }

    engine.export_behavior(behavior_data)
    behavior_file = vault_path / "behaviors" / "login-flow.md"
    assert os.path.exists(behavior_file)
    with open(behavior_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "## Behavioral Characteristics & Safety Constraints" in content
    # For REQUEST_RECEIVED:
    # Loops: loop (for/while/foreach)
    # Conditions: conditionals (if/else/switch)
    # Boundaries: `item.val >= 100`
    # Recovery: exception handling / try-catch
    # Performance: database operations
    assert "loop (for/while/foreach)" in content
    assert "conditionals (if/else/switch)" in content
    assert "`item.val >= 100`" in content
    assert "exception handling / try-catch" in content
    assert "database operations" in content

    # For VALIDATING:
    # Stress/Performance: timeout configuration
    assert "timeout configuration" in content


