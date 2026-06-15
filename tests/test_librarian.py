import pytest
import os
import time
import json
from unittest.mock import MagicMock, patch
from brain.librarian import LibrarianEngine

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

    symbol_data = {
        "name": "validateToken",
        "language": "cpp",
        "file": "src/auth.cpp",
        "signature": "bool validateToken(string t)",
        "docstring": "Validates a jwt token.",
        "params": [{"name": "t", "type": "string", "description": "token string"}],
        "returns": {"type": "bool", "description": "true if valid"},
        "business_rules": ["Validates expiry", "Checks signature"]
    }

    engine.export_symbol(symbol_data)
    symbol_file = vault_path / "symbols" / "validateToken.md"
    assert os.path.exists(symbol_file)
    with open(symbol_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "type: symbol" in content
    assert "name: validateToken" in content
    assert "Mermaid" not in content  # basic symbols don't have mermaid unless mapped to behavior

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
    assert "[[badFunc]]" in content
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
    assert "[[tooLongFunction]]" in content
    assert "Function is too long (> 50 lines)" in content

