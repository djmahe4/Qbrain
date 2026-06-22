import os
import pytest
from unittest.mock import MagicMock
from brain.librarian import LibrarianEngine
from brain.config import Config
from brain.indexer import Indexer

@pytest.fixture
def temp_vault(tmp_path):
    vault_dir = os.path.join(tmp_path, "vault")
    repo_dir = os.path.join(tmp_path, "repo")
    os.makedirs(vault_dir, exist_ok=True)
    os.makedirs(repo_dir, exist_ok=True)
    return repo_dir, vault_dir

@pytest.fixture
def real_indexer(temp_vault):
    repo_dir, vault_dir = temp_vault
    config = Config()
    config.repo_path = repo_dir
    config.data["vault_path"] = vault_dir
    config.data["cbm_binary"] = "codebase-memory-mcp"
    return Indexer(config)

def test_confidence_tiered_exports(temp_vault, real_indexer):
    repo_dir, vault_dir = temp_vault
    engine = LibrarianEngine(repo_dir, vault_dir, indexer=real_indexer)
    engine.setup_vault()
    
    # 1. High Confidence Symbol (Docstring + Taint + Callers)
    # Expected Score: 0.4 (docstring) + 0.3 (taint) + 0.2 (2 callers) = 0.9 >= 0.5 -> Full Page
    high_conf = {
        "name": "src/app.py:process_data",
        "kind": "Function",
        "language": "python",
        "file": "src/app.py",
        "docstring": "This processes important sensitive data.",
        "params": [],
        "returns": {},
        "business_rules": [],
        "mass": 1.0,
        "potential_energy": 0.0,
        "archetype": "generic",
        "callers": ["caller1", "caller2"],
        "callees": [],
        "vulnerabilities": [],
        "variable_states": {"_TAINT_": "PRIVILEGE_LABEL"}, # has taint
        "flow_paths": [],
        "behaviors": []
    }
    
    # 2. Medium Confidence Symbol (No docstring, no taint, 2 callers)
    # Expected Score: 0.2 (2 callers) = 0.2 (which is between 0.1 and 0.49) -> Stub Page
    med_conf = {
        "name": "src/app.py:simple_getter",
        "kind": "Function",
        "language": "python",
        "file": "src/app.py",
        "docstring": "",
        "params": [],
        "returns": {},
        "business_rules": [],
        "mass": 1.0,
        "potential_energy": 0.0,
        "archetype": "generic",
        "callers": ["caller1", "caller2"],
        "callees": [],
        "vulnerabilities": [],
        "variable_states": {},
        "flow_paths": [],
        "behaviors": []
    }
    
    # 3. Low Confidence Symbol (No docstring, no taint, no callers, no entanglements)
    # Expected Score: 0.0 < 0.1 -> Skip Page
    low_conf = {
        "name": "src/app.py:dead_code",
        "kind": "Function",
        "language": "python",
        "file": "src/app.py",
        "docstring": "",
        "params": [],
        "returns": {},
        "business_rules": [],
        "mass": 1.0,
        "potential_energy": 0.0,
        "archetype": "generic",
        "callers": [],
        "callees": [],
        "vulnerabilities": [],
        "variable_states": {},
        "flow_paths": [],
        "behaviors": []
    }
    
    engine.export_symbol(high_conf)
    engine.export_symbol(med_conf)
    engine.export_symbol(low_conf)
    
    symbols_dir = os.path.join(vault_dir, "symbols")
    
    # Verify High Confidence file is a FULL export
    high_file = os.path.join(symbols_dir, "src_app_py_process_data.md")
    assert os.path.exists(high_file)
    with open(high_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "## Documentation" in content  # Full page details exist
        
    # Verify Medium Confidence file is a STUB export
    med_file = os.path.join(symbols_dir, "src_app_py_simple_getter.md")
    assert os.path.exists(med_file)
    with open(med_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "type: symbol" in content
        assert "## Documentation" not in content  # Detailed documentation should be omitted in stub
        
    # Verify Low Confidence file is SKIPPED
    low_file = os.path.join(symbols_dir, "src_app_py_dead_code.md")
    assert not os.path.exists(low_file)

    # Verify confidence scores in SQLite DB
    assert real_indexer.persistence.get_symbol_confidence("src/app.py:process_data") == pytest.approx(0.9)
    assert real_indexer.persistence.get_symbol_confidence("src/app.py:simple_getter") == pytest.approx(0.2)
    assert real_indexer.persistence.get_symbol_confidence("src/app.py:dead_code") == pytest.approx(0.0)
