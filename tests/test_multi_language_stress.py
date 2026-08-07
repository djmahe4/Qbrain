import os
import json
import pytest
import subprocess
import numpy as np
from brain.cli import get_cognitive_engine
from brain.commands.library import sync_library
from brain.quantum_correlator import QuantumCorrelator
from rich.console import Console

@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = os.path.join(tmp_path, "repo")
    vault_dir = os.path.join(tmp_path, "vault")
    os.makedirs(repo_dir, exist_ok=True)
    os.makedirs(vault_dir, exist_ok=True)
    return repo_dir, vault_dir

def test_multi_language_stress_real_simulation(temp_repo, monkeypatch):
    """
    Stress test multi/cross-language indexing, docstring genomes, and
    quantum correlation by running the actual codebase_memory_mcp toolchain.
    """
    repo_dir, vault_dir = temp_repo
    
    # 1. Initialize git in temp_repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Stress User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "stress@example.com"], cwd=repo_dir, check=True)
    
    # 2. Write multi-language files
    src_dir = os.path.join(repo_dir, "src")
    os.makedirs(src_dir, exist_ok=True)
    
    # Python file
    py_file = os.path.join(src_dir, "math.py")
    with open(py_file, "w", encoding="utf-8") as f:
        f.write(
            "def add_numbers(a, b):\n"
            "    \"\"\"\n"
            "    Adds two numbers.\n"
            "    \"\"\"\n"
            "    if a < 0:\n"
            "        raise ValueError('a is negative')\n"
            "    return a + b\n"
        )
        
    # Go file referencing C++
    go_file = os.path.join(src_dir, "auth.go")
    with open(go_file, "w", encoding="utf-8") as f:
        f.write(
            "package main\n\n"
            "// AuthenticateUser verifies a user's session token.\n"
            "// Calls the C++ security validator `validate_token_checksum`.\n"
            "func AuthenticateUser(token string) bool {\n"
            "    if len(token) < 16 {\n"
            "        return false\n"
            "    }\n"
            "    return true\n"
            "}\n"
        )
        
    # C++ file
    cpp_file = os.path.join(src_dir, "validator.cpp")
    with open(cpp_file, "w", encoding="utf-8") as f:
        f.write(
            "#include <string>\n\n"
            "// validate_token_checksum verifies the cryptographic checksum.\n"
            "// Ensures it is safe but winner contradicts.\n"
            "bool validate_token_checksum(std::string token) {\n"
            "    if (token.empty()) {\n"
            "        return false;\n"
            "    }\n"
            "    return true;\n"
            "}\n"
        )
        
    # JavaScript file
    js_file = os.path.join(src_dir, "utils.js")
    with open(js_file, "w", encoding="utf-8") as f:
        f.write(
            "/**\n"
            " * Formats a string message.\n"
            " */\n"
            "function formatMessage(msg) {\n"
            "    const x = msg;\n"
            "    if (!x) {\n"
            "        return 'empty';\n"
            "    }\n"
            "    return x.trim();\n"
            "}\n"
        )
        
    # Solidity file
    sol_file = os.path.join(src_dir, "contract.sol")
    with open(sol_file, "w", encoding="utf-8") as f:
        f.write(
            "pragma solidity ^0.8.0;\n\n"
            "contract Bank {\n"
            "    // deposit accepts funds from sender.\n"
            "    function deposit() public payable {\n"
            "        require(msg.value > 0);\n"
            "    }\n"
            "}\n"
        )
        
    # Rust file
    rs_file = os.path.join(src_dir, "crypto.rs")
    with open(rs_file, "w", encoding="utf-8") as f:
        f.write(
            "/// execute_hash calculates SHA256.\n"
            "pub fn execute_hash(data: &str) -> String {\n"
            "    let x = data;\n"
            "    x.to_string()\n"
            "}\n"
        )

    # Commit all
    subprocess.run(["git", "add", "src/"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Add multi-language source files"], cwd=repo_dir, check=True)
    
    # 3. Setup configuration
    config_data = {
        "repo_path": repo_dir.replace("\\", "/"),
        "vault_path": vault_dir.replace("\\", "/"),
        "correlation_threshold": 0.2
    }
    config_file = os.path.join(repo_dir, ".quantum-brain.json")
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
        
    monkeypatch.chdir(repo_dir)
    
    # 4. Initialize Engines
    config, indexer, embedder, scorer, store, cem, san, cognitive, api = get_cognitive_engine()
    
    # Index using codebase_memory_mcp
    res = indexer.index_repository(repo_dir)
    assert res.get("project") is not None
    
    # Sync Librarian to generate Obsidian Vault notes and SQLite files
    sync_library(config, indexer, Console())
    
    # Run the physics scoring simulator
    from brain.commands.monitor import score_graph
    score_graph(5, config, indexer, embedder, scorer, Console())
    
    # Retrieve beliefs to verify SQLite is populated
    beliefs = indexer.persistence.get_all_variable_states()
    assert len(beliefs) > 0
    
    # Verify that all 6 target languages are represented in the graph
    all_funcs = indexer.query_graph("MATCH (f:Function) RETURN f.name AS name, f.qualified_name AS qualified_name, f.file AS file")
    symbol_identifiers = []
    for f in all_funcs:
        if f.get("qualified_name"):
            symbol_identifiers.append(f["qualified_name"])
        if f.get("file"):
            symbol_identifiers.append(f["file"])
        if f.get("name"):
            symbol_identifiers.append(f["name"])
            
    assert any(".math." in sym for sym in symbol_identifiers), f"Symbol identifiers were: {symbol_identifiers}"
    assert any(".auth." in sym for sym in symbol_identifiers)
    assert any(".validator." in sym for sym in symbol_identifiers)
    assert any(".utils." in sym for sym in symbol_identifiers)
    assert any(".contract." in sym for sym in symbol_identifiers)
    assert any(".crypto." in sym for sym in symbol_identifiers)
    
    # 5. Verify QuantumCorrelator can run entanglement over real multi-language files
    from brain.docstring_parser import DocstringParser
    doc_parser = DocstringParser(indexer)
    comments = doc_parser.get_functions_with_docstrings()
    assert len(comments) >= 5  # at least 5 of our functions have docstrings/comments
    
    correlator = QuantumCorrelator()
    pairs = correlator.entangle(comments, beliefs, embedder, threshold=0.2)
    assert isinstance(pairs, list)
    
    # Detect flips and decoherence on real simulated data
    pairs = correlator.detect_flips(pairs, beliefs)
    qualified_symbols = set(f["qualified_name"] for f in all_funcs if f.get("qualified_name"))
    pairs = correlator.detect_decoherence(pairs, qualified_symbols)
    assert all(isinstance(p.flip_detected, bool) for p in pairs)
    assert all(isinstance(p.decoherence, bool) for p in pairs)
