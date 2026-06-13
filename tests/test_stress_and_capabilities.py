import pytest
import os
import random
import numpy as np
import yaml
from unittest.mock import MagicMock
from brain.config import Config
from brain.language_parser import LanguageParser, detect_language
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.librarian import LibrarianEngine
from brain.indexer import Indexer

def test_language_parser_missing_docstrings():
    parser = LanguageParser()
    languages = ["python", "javascript", "typescript", "solidity", "rust", "go", "cpp", "generic"]

    for lang in languages:
        # Test None docstring
        record_none = {
            "name": f"test_none_{lang}",
            "file": f"src/test.{lang}",
            "docstring": None,
            "signature": "void run()",
            "language": lang
        }
        genome_none = parser.parse(record_none)
        assert genome_none["name"] == f"test_none_{lang}"
        assert genome_none["docstring"] == ""
        assert genome_none["params"] == []
        assert genome_none["returns"] == {"type": "", "description": ""}
        assert genome_none["business_rules"] == []

        # Test empty docstring
        record_empty = {
            "name": f"test_empty_{lang}",
            "file": f"src/test.{lang}",
            "docstring": "   ",
            "signature": "void run()",
            "language": lang
        }
        genome_empty = parser.parse(record_empty)
        assert genome_empty["name"] == f"test_empty_{lang}"
        assert genome_empty["params"] == []
        assert genome_empty["returns"] == {"type": "", "description": ""}

def test_language_parser_malformed_comments():
    parser = LanguageParser()
    
    # Malformed JSDoc
    record_js = {
        "name": "jsFunc",
        "file": "src/test.js",
        "docstring": "/** @param invalid type format } foo @returns {incomplete */",
        "language": "javascript"
    }
    genome_js = parser.parse(record_js)
    assert len(genome_js["params"]) >= 0  # Should parse gracefully or return empty, no exception
    assert isinstance(genome_js["returns"], dict)

    # Malformed Python docstring (no structure, empty parameters header)
    record_py = {
        "name": "pyFunc",
        "file": "src/test.py",
        "docstring": "Parameters:\n-----------\nInvalid indented line\nReturns:\n-------",
        "language": "python"
    }
    genome_py = parser.parse(record_py)
    assert isinstance(genome_py["params"], list)
    assert "type" in genome_py["returns"]
    assert "description" in genome_py["returns"]

    # Malformed Doxygen
    record_cpp = {
        "name": "cppFunc",
        "file": "src/test.cpp",
        "docstring": "/// @param [in,out] @returns",
        "language": "cpp"
    }
    genome_cpp = parser.parse(record_cpp)
    assert isinstance(genome_cpp["params"], list)
    assert isinstance(genome_cpp["returns"], dict)

def test_stress_quantum_scorer_performance_bh():
    config = Config()
    scorer = QuantumScorer(config, MagicMock())
    
    # Generate 600 nodes (threshold for Barnes-Hut is > 500)
    nodes = []
    dim = 384  # typical embed size
    for i in range(600):
        emb = np.random.rand(dim)
        emb /= np.linalg.norm(emb)
        node = FunctionNode(
            name=f"func_{i}",
            embedding=emb,
            complexity=random.uniform(1.0, 10.0),
            side_effects=random.uniform(0.0, 1.0),
            is_exported=random.choice([True, False])
        )
        nodes.append(node)

    # Run physical simulation using Barnes-Hut quadtree
    scorer.run_simulation(nodes, iterations=5)
    
    # Check that scores were generated successfully
    for n in nodes:
        assert 0.0 <= n.business_score <= 1.0
        assert n.quantum_state in ("collapsed_business", "collapsed_utility", "collapsed_neutral")

def test_stress_quantum_scorer_dense_positions():
    config = Config()
    scorer = QuantumScorer(config, MagicMock())
    
    # Create nodes with identical semantic embeddings (semantic_distance = 0) and overlapping starting positions
    emb = np.ones(128)
    emb /= np.linalg.norm(emb)
    
    nodes = [
        FunctionNode("fn1", emb.copy()),
        FunctionNode("fn2", emb.copy()),
        FunctionNode("fn3", emb.copy())
    ]
    
    # Force initial positions to be exactly identical
    for fn in nodes:
        fn.position = [0.1, 0.1]
        
    # Run simulation: should nudging solve coordinate overlaps without throwing division by zero?
    scorer.run_simulation(nodes, iterations=10)
    
    for fn in nodes:
        assert not np.isnan(fn.position[0])
        assert not np.isnan(fn.position[1])

def test_stress_librarian_lock_concurrency(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))

    # Lock acquisition
    with engine.lock():
        # A second attempt to lock from same engine instance/thread is blocked
        with pytest.raises(RuntimeError):
            with engine.lock():
                pass

def test_stress_config_merging_complex(tmp_path):
    # Setup custom override .qbrain-rules.yaml with deeply nested configs
    rules_data = {
        "history": {
            "keep_threshold": 42,
            "weights": {
                "security_change": 99,
                "behavior_change": 88
            },
            "ignore": ["*.ts", "build/"]
        }
    }
    rules_file = tmp_path / ".qbrain-rules.yaml"
    rules_file.write_text(yaml.dump(rules_data))

    config = Config()
    config.data["repo_path"] = str(tmp_path)
    config._load_rules_config()

    # Core parameters should be merged
    assert config.data["rules"]["history"]["keep_threshold"] == 42
    assert config.data["rules"]["history"]["weights"]["security_change"] == 99
    assert config.data["rules"]["history"]["weights"]["behavior_change"] == 88
    # Glob ignores overridden
    assert "*.ts" in config.data["rules"]["history"]["ignore"]
    # Fallback weights preserved
    assert config.data["rules"]["history"]["weights"]["symbol_change"] == 3
