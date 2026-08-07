import os
import pytest
import numpy as np
from unittest.mock import MagicMock
from brain.quantum_correlator import QuantumCorrelator, EntangledPair
from brain.persistence_manager import PersistenceManager
from brain.config import Config
from brain.indexer import Indexer
from brain.embedder import Embedder

class FakeEmbedder:
    def embed(self, texts):
        if isinstance(texts, str):
            return self._to_vec(texts)
        return np.array([self._to_vec(t) for t in texts])

    def _to_vec(self, text):
        t_low = text.lower()
        if "login" in t_low or "auth" in t_low:
            return np.array([1.0, 0.0, 0.0])
        if "sql" in t_low or "query" in t_low:
            return np.array([0.0, 1.0, 0.0])
        return np.array([0.0, 0.0, 1.0])

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

def test_quantum_correlator_entanglement():
    correlator = QuantumCorrelator()
    embedder = FakeEmbedder()

    comments = [
        {
            "name": "src/auth.py:login_user",
            "docstring": "Authenticates a user against secure credentials.",
            "file": "src/auth.py",
            "line": 10
        },
        {
            "name": "src/db.py:run_query",
            "docstring": "Executes raw SQL query on database.",
            "file": "src/db.py",
            "line": 20
        }
    ]

    beliefs = {
        "src/auth.py:login_user": {"winner": "SAFE", "beliefs": {}},
        "src/db.py:run_query": {"winner": "TAINTED", "beliefs": {}}
    }

    pairs = correlator.entangle(comments, beliefs, embedder, threshold=0.7)
    
    assert len(pairs) == 2
    pair1 = next(p for p in pairs if p.symbol_name == "src/auth.py:login_user")
    assert pair1.cosine_score > 0.7
    
    pair2 = next(p for p in pairs if p.symbol_name == "src/db.py:run_query")
    assert pair2.cosine_score > 0.7

def test_quantum_correlator_detect_flips():
    correlator = QuantumCorrelator()
    
    pairs = [
        EntangledPair(
            comment_text="Sanitizes input before passing to query.",
            comment_file="src/db.py",
            comment_line=15,
            symbol_name="src/db.py:run_query",
            cosine_score=0.9,
            flip_detected=False,
            flip_reason="",
            decoherence=False
        ),
        EntangledPair(
            comment_text="Public endpoint unauthenticated access permitted.",
            comment_file="src/admin.py",
            comment_line=5,
            symbol_name="src/admin.py:delete_all",
            cosine_score=0.85,
            flip_detected=False,
            flip_reason="",
            decoherence=False
        )
    ]

    beliefs = {
        "src/db.py:run_query": {"winner": "TAINTED", "beliefs": {}},
        "src/admin.py:delete_all": {"winner": "SAFE", "beliefs": {}}
    }

    pairs = correlator.detect_flips(pairs, beliefs)

    assert pairs[0].flip_detected
    assert "contradicts" in pairs[0].flip_reason

    assert pairs[1].flip_detected
    assert "auth-required" in pairs[1].flip_reason

def test_quantum_correlator_detect_decoherence():
    correlator = QuantumCorrelator()

    pairs = [
        EntangledPair(
            comment_text="This references historical `old_cleanup` function.",
            comment_file="src/db.py",
            comment_line=15,
            symbol_name="src/db.py:run_query",
            cosine_score=0.9,
            flip_detected=False,
            flip_reason="",
            decoherence=False
        )
    ]

    graph_symbols = {"src/db.py:run_query", "src/auth.py:login_user"}
    pairs = correlator.detect_decoherence(pairs, graph_symbols)

    assert pairs[0].decoherence
    assert "old_cleanup" in pairs[0].flip_reason

def test_quantum_correlator_real_integration(temp_vault, real_indexer):
    repo_dir, vault_dir = temp_vault
    embedder = Embedder()
    correlator = QuantumCorrelator()
    
    # Initialize some beliefs in DB
    real_indexer.persistence.persist_belief("src/auth.py:login_user", {
        "beliefs": {"SAFE": 1.0},
        "status": "ACTIVE",
        "winner": "SAFE",
        "support_mass": 1.0,
        "potential_energy": 0.0
    })
    real_indexer.persistence.persist_belief("src/db.py:run_query", {
        "beliefs": {"TAINTED": 1.0},
        "status": "ACTIVE",
        "winner": "TAINTED",
        "support_mass": 1.0,
        "potential_energy": 0.0
    })

    comments = [
        {
            "name": "src/auth.py:login_user",
            "docstring": "Authenticates user login against credentials.",
            "file": "src/auth.py",
            "line": 10
        },
        {
            "name": "src/db.py:run_query",
            "docstring": "Executes raw SQL query on database.",
            "file": "src/db.py",
            "line": 20
        }
    ]

    beliefs = real_indexer.persistence.get_all_variable_states()
    
    # Perform entanglement and checks
    pairs = correlator.entangle(comments, beliefs, embedder, threshold=0.3)
    assert len(pairs) > 0
    
    pairs = correlator.detect_flips(pairs, beliefs)
    pairs = correlator.detect_decoherence(pairs, {"src/auth.py:login_user", "src/db.py:run_query"})
    
    correlator.persist(pairs, real_indexer.persistence)
    
    # Verify they exist in database
    db_ents = real_indexer.persistence.get_internal_entanglements()
    assert len(db_ents) > 0


def test_quantum_correlator_stress():
    import time
    correlator = QuantumCorrelator()
    
    class RandomEmbedder:
        def embed(self, texts):
            return np.random.rand(len(texts), 384)
            
    embedder = RandomEmbedder()
    
    comments = [
        {"docstring": f"This is comment {i}", "file": f"src/file_{i}.py", "line": "invalid_int" if i % 10 == 0 else i}
        for i in range(1000)
    ]
    
    beliefs = {
        f"src/file_{i}.py:func_{i}": {"winner": "TAINTED" if i % 3 == 0 else "SAFE", "beliefs": {}}
        for i in range(1000)
    }
    
    start_time = time.perf_counter()
    pairs = correlator.entangle(comments, beliefs, embedder, threshold=0.1)
    duration = time.perf_counter() - start_time
    
    # Enforce performance: 1000x1000 matching should take less than 1.0 second
    assert duration < 1.0
    
    # Test flip and decoherence detection on stress scale
    pairs = correlator.detect_flips(pairs, beliefs)
    graph_symbols = {f"src/file_{i}.py:func_{i}" for i in range(1000) if i % 2 == 0}
    pairs = correlator.detect_decoherence(pairs, graph_symbols)

def test_decoherence_filter_refined():
    correlator = QuantumCorrelator()
    pairs = [
        EntangledPair(
            comment_text="This public class returns null, true, false, and references ghost_func or GhostClass.",
            comment_file="src/db.py",
            comment_line=15,
            symbol_name="src/db.py:run_query",
            cosine_score=0.9,
            flip_detected=False,
            flip_reason="",
            decoherence=False
        )
    ]
    graph_symbols = {"src/db.py:run_query"}
    pairs = correlator.detect_decoherence(pairs, graph_symbols)
    
    assert pairs[0].decoherence
    # ghost_func and GhostClass should be flagged as ghosts
    assert "ghost_func" in pairs[0].flip_reason
    assert "GhostClass" in pairs[0].flip_reason
    # Standard keywords like 'public', 'class', 'null', 'true', 'false' should NOT be flagged
    assert "public" not in pairs[0].flip_reason
    assert "class" not in pairs[0].flip_reason
    assert "null" not in pairs[0].flip_reason
    assert "true" not in pairs[0].flip_reason
    assert "false" not in pairs[0].flip_reason


