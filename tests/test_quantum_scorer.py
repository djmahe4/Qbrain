import pytest
import numpy as np
from unittest.mock import MagicMock
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.config import Config

def test_write_physics_to_graph_batching():
    config = Config()
    config.data["quantum_gravity_constant"] = 1.0
    config.data["repulsive_constant"] = 0.05

    class SpyIndexer:
        def __init__(self):
            self.queries = []
            # Mock PersistenceManager to avoid SQLite creation in tests
            self.persistence = MagicMock()
        def query_graph(self, cypher):
            self.queries.append(cypher)
            return []
        def _get_project_name(self):
            return "test-project"

    indexer = SpyIndexer()
    scorer = QuantumScorer(config, indexer)

    v1 = np.array([1.0, 0.0])
    v2 = np.array([0.0, 1.0])
    v3 = np.array([0.707, 0.707])

    f1 = FunctionNode("f1", v1)
    f2 = FunctionNode("f2", v2)
    f3 = FunctionNode("f3", v3)

    funcs = [f1, f2, f3]
    scorer.run_simulation(funcs, iterations=1)
    scorer.write_physics_to_graph(funcs)

    # We expect calls to persist_physics on the persistence mock
    assert indexer.persistence.persist_physics.call_count == 3

def test_simulation_stress_1000_nodes():
    from brain.config import Config
    from brain.indexer import Indexer
    config = Config()
    
    # Use a dummy repo path for test
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        config.data["repo_path"] = tmp
        indexer = Indexer(config)
        scorer = QuantumScorer(config, indexer)
        nodes = []
        
        for i in range(100): # Reduced for faster unit test, separate stress test exists
            emb = np.random.rand(384).astype(np.float32)
            node = FunctionNode(
                name=f"func_{i}",
                embedding=emb,
                complexity=1.0,
                side_effects=0.0,
                is_exported=True
            )
            nodes.append(node)
            
        scorer.run_simulation(nodes, iterations=5)
        for node in nodes:
            assert not np.isnan(node.position[0])
            assert node.business_score >= 0.0
