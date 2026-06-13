import pytest
import os
import json
import shutil
import tempfile
from brain.config import Config
from brain.indexer import Indexer
from brain.git_watcher import GitWatcher
from brain.librarian import LibrarianEngine
from brain.commands import index, monitor, library

def test_full_pipeline_circuit(mocker, tmp_path):
    repo_path = os.path.join(tmp_path, "repo")
    vault_path = os.path.join(tmp_path, "vault")
    os.makedirs(repo_path)
    os.makedirs(vault_path)
    
    # 1. Setup Config
    config_file = os.path.join(repo_path, ".quantum-brain.json")
    config_data = {
        "repo_path": repo_path,
        "vault_path": vault_path
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
        
    config = Config(config_file)
    indexer = Indexer(config)
    
    # 2. Mock Indexer response for symbols
    mock_functions = [
        {
            "name": "calculate_total",
            "file": "math.py",
            "signature": "def calculate_total(items: list) -> float",
            "docstring": "Calculates the total of all items.\n@param items: list of prices",
            "complexity": 2.0
        }
    ]
    
    # Mocking query_graph to return our function
    mocker.patch.object(Indexer, "query_graph", return_value=mock_functions)
    mocker.patch("brain.docstring_parser.DocstringParser.get_functions_with_docstrings", return_value=mock_functions)
    mocker.patch.object(Indexer, "index_repository", return_value={"status": "indexed"})
    mocker.patch.object(Indexer, "get_code_snippet", return_value={"code": "def calculate_total(items): return sum(items)"})

    # 3. Simulate Index
    from rich.console import Console
    console = Console()
    index.index_repo(repo_path, config, indexer, console)
    
    # 4. Simulate Library Sync
    # We need to ensure DocstringParser is used correctly in library.py
    # Since library.sync_library calls get_engine(), we might need to mock that or pass dependencies
    
    # Let's just call the engine directly to verify its behavior in the pipeline
    lib_engine = LibrarianEngine(repo_path, vault_path)
    library.sync_library(config, indexer, console)
    
    # 5. Verify Vault
    symbol_file = os.path.join(vault_path, "symbols", "calculate_total.md")
    assert os.path.exists(symbol_file)
    with open(symbol_file, "r") as f:
        content = f.read()
        assert "calculate_total" in content
        assert "math.py" in content
        
    # 6. Simulate Change & Watcher
    mock_diff = {
        "head": "commit2",
        "base": "commit1",
        "modified_files": ["math.py"],
        "affected_symbols": [{"name": "calculate_total"}],
        "has_behavior": True
    }
    mocker.patch.object(Indexer, "detect_changes", return_value=mock_diff)
    
    from brain.embedder import Embedder
    from brain.quantum_scorer import QuantumScorer
    embedder = Embedder()
    scorer = QuantumScorer(config, indexer)
    watcher = GitWatcher(config, indexer, scorer, embedder)
    # Manually check diff
    mocker.patch("subprocess.check_output", return_value="commit2")
    watcher.check_diff()
    # Verify watcher state
    state_file = os.path.join(repo_path, ".quantum-brain-state.json")
    assert os.path.exists(state_file)
    with open(state_file, "r") as f:
        state = json.load(f)
        assert state["last_commit"] == "commit2"
