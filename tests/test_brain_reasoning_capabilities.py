import pytest
import numpy as np
from unittest.mock import MagicMock
from brain.config import Config
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.quantum_correlator import QuantumCorrelator, EntangledPair

class SemanticMockEmbedder:
    """
    A mock embedder that returns pre-defined vectors based on semantic concepts
    to simulate a real embedding model's cosine similarities.
    """
    def embed(self, texts):
        if isinstance(texts, str):
            return self._get_vector(texts)
        return np.array([self._get_vector(t) for t in texts])

    def _get_vector(self, text):
        t_low = text.lower()
        # Concept 1: Authentication / Login
        if any(w in t_low for w in ["auth", "login", "credentials", "session"]):
            return np.array([1.0, 0.1, 0.0, 0.0])
        # Concept 2: Database / SQL Query
        if any(w in t_low for w in ["sql", "query", "database", "select"]):
            return np.array([0.1, 1.0, 0.0, 0.0])
        # Concept 3: Utility / Hashing
        if any(w in t_low for w in ["hash", "md5", "encrypt", "crypto"]):
            return np.array([0.0, 0.0, 1.0, 0.1])
        # Default fallback: generate a deterministic unit vector using a local seed to prevent singularities
        h = hash(text) & 0xffffffff
        rng = np.random.default_rng(h)
        vec = rng.normal(0, 1, 4)
        return vec / np.linalg.norm(vec)

def test_brain_cognitive_reasoning_capabilities():
    """
    Verify the brain's reasoning capabilities over a simulated multi-language codebase.
    We test:
    1. Archetype Collapse: High-centrality auth symbols collapse to 'system-hub', utilities to 'utility'.
    2. Intent Flips: Mismatch between comment validation claims and TAINTED symbol winners.
    3. Decoherence: Comments referencing missing symbols (ghosts).
    4. SLM Context Generation: Synthesis of the reasoning state.
    """
    config = Config()
    config.data["quantum_gravity_constant"] = 1.0
    config.data["repulsive_constant"] = 0.1
    config.data["business_collapse_threshold"] = 0.6
    
    indexer = MagicMock()
    scorer = QuantumScorer(config, indexer)
    correlator = QuantumCorrelator()
    embedder = SemanticMockEmbedder()

    # 1. Define multi-language symbols with varying complexity, side effects, and exports
    # PHP Auth Controller (High complexity, exported, acts as a system hub)
    auth_controller = FunctionNode(
        name="vulnerabilities/api/src/LoginController.php:loginUser",
        embedding=embedder.embed("Authenticates user credentials and establishes secure session"),
        complexity=8.0,
        side_effects=5.0,
        is_exported=True,
        file="vulnerabilities/api/src/LoginController.php",
        line=45
    )
    
    # PHP Database Access (Medium complexity, tainted SQL sink)
    db_query = FunctionNode(
        name="dvwa/includes/DBMS_MySQL.php:executeRawQuery",
        embedding=embedder.embed("Executes raw SQL query on the database"),
        complexity=4.0,
        side_effects=8.0,
        is_exported=False,
        file="dvwa/includes/DBMS_MySQL.php",
        line=120
    )
    
    # Python Encryption Helper (Low complexity, private utility)
    crypto_helper = FunctionNode(
        name="helpers/crypto.py:hash_password",
        embedding=embedder.embed("Computes secure md5/sha256 hash of password"),
        complexity=1.0,
        side_effects=0.0,
        is_exported=False,
        file="helpers/crypto.py",
        line=12
    )

    funcs = [auth_controller, db_query, crypto_helper]
    
    # Add 15 dummy utility/standard nodes spread out semantically to create a realistic graph
    # We add a small amount of noise to prevent them from sharing identical coordinates (singularity)
    for i in range(15):
        base_emb = embedder.embed(f"simple formatting utility function number {i}")
        noise = np.random.normal(0, 0.05, base_emb.shape)
        funcs.append(FunctionNode(
            name=f"utils/helper_{i}.py:format_data_{i}",
            embedding=base_emb + noise,
            complexity=1.0,
            side_effects=0.0,
            is_exported=False,
            file=f"utils/helper_{i}.py",
            line=5
        ))

    # Run the scoring simulation to collapse the nodes into archetypes
    scorer.run_simulation(funcs, iterations=15)

    print("\n--- DEBUG NODE SCORES ---")
    for f in funcs[:5]:
        print(f"Name: {f.name}")
        print(f"  Mass: {f.mass:.3f}")
        print(f"  PE: {f.potential_energy:.3f}")
        print(f"  Business Score: {f.business_score:.3f}")
        print(f"  State: {f.quantum_state}")

    # Verify Archetype Collapse based on cognitive mass and centrality
    # Auth Controller should be a system-hub or core-logic due to its high mass
    assert auth_controller.quantum_state in ["system-hub", "core-logic"]
    # Crypto helper should collapse to utility or standard-module
    assert crypto_helper.quantum_state in ["utility", "standard-module"]
    # Verify that both major core nodes have significantly higher scores than the utility helper
    assert auth_controller.business_score > crypto_helper.business_score
    assert db_query.business_score > crypto_helper.business_score

    # 2. Define comments extracted from the codebase to test semantic entanglement and flips
    comments = [
        {
            # Intent Flip: Comment claims validation, but static analysis marked the winner as TAINTED
            "name": "dvwa/includes/DBMS_MySQL.php:executeRawQuery",
            "docstring": "Sanitizes and checks the input before running the SQL query.",
            "file": "dvwa/includes/DBMS_MySQL.php",
            "line": 118
        },
        {
            # Decoherence: Comment references a deleted function `old_auth_check`
            "name": "vulnerabilities/api/src/LoginController.php:loginUser",
            "docstring": "Performs authentication. Historically called `old_auth_check` to verify tokens.",
            "file": "vulnerabilities/api/src/LoginController.php",
            "line": 42
        }
    ]

    # Mock beliefs where the database query is TAINTED (e.g., SQL Injection risk)
    beliefs = {
        "vulnerabilities/api/src/LoginController.php:loginUser": {"winner": "SAFE", "beliefs": {}},
        "dvwa/includes/DBMS_MySQL.php:executeRawQuery": {"winner": "TAINTED", "beliefs": {}},
        "helpers/crypto.py:hash_password": {"winner": "SAFE", "beliefs": {}}
    }

    # Perform Entanglement mapping
    pairs = correlator.entangle(comments, beliefs, embedder, threshold=0.6)
    assert len(pairs) == 2

    # Run Flip Detection (should catch the contradiction in the database query comment)
    pairs = correlator.detect_flips(pairs, beliefs)
    flip_pair = next(p for p in pairs if "DBMS_MySQL.php" in p.comment_file)
    assert flip_pair.flip_detected
    assert "contradicts" in flip_pair.flip_reason

    # Run Decoherence Detection (should catch the reference to the ghost symbol `old_auth_check`)
    graph_symbols = {f.name for f in funcs}
    pairs = correlator.detect_decoherence(pairs, graph_symbols)
    deco_pair = next(p for p in pairs if "LoginController.php" in p.comment_file)
    assert deco_pair.decoherence
    assert "old_auth_check" in deco_pair.flip_reason
    # Verify standard keywords in the comment (like 'class', 'returns') are NOT flagged as ghosts
    assert "returns" not in deco_pair.flip_reason

    # 3. Generate the final SLM context summary and verify its reasoning value
    summary = correlator.to_context_summary(pairs)
    assert "FLIP" in summary
    assert "DECOHERENCE" in summary
    assert "DBMS_MySQL.php" in summary
    assert "LoginController.php" in summary
    
    print("\nGenerated SLM Reasoning Context:\n", summary)
