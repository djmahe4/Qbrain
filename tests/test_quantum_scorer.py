import pytest
import numpy as np
from brain.quantum_scorer import FunctionNode, QuantumScorer
from brain.config import Config

class MockIndexer:
    def query_graph(self, cypher):
        return []

def test_mass_calculation():
    # Base mass = 1.0
    f1 = FunctionNode("test1", np.array([1.0, 0.0]), complexity=2.0, side_effects=1.0, is_exported=True)
    # 1.0 + 2*0.3 + 1*0.5 + 2.0 = 4.1
    assert abs(f1.mass - 4.1) < 1e-5

def test_forces_and_potential():
    config = Config()
    config.data["quantum_gravity_constant"] = 1.0
    config.data["repulsive_constant"] = 0.05
    indexer = MockIndexer()

    scorer = QuantumScorer(config, indexer)

    # Identical vectors -> distance ~0
    # Let's create orthogonal vectors for distance = 1.0
    v1 = np.array([1.0, 0.0])
    v2 = np.array([0.0, 1.0])

    f1 = FunctionNode("f1", v1, complexity=0, side_effects=0, is_exported=False)
    f2 = FunctionNode("f2", v2, complexity=0, side_effects=0, is_exported=False)

    # Both mass = 1.0
    # Gravitational force: 1.0 * (1*1) / 1^2 = 1.0
    # Repulsive force: 0.05 / 1.0 = 0.05
    # Net force = 0.95
    f_net = scorer.net_force(f1, f2, 1.0)
    assert abs(f_net - 0.95) < 1e-5

    # Potential energy: -1.0 * (1*1) / 1.0 = -1.0
    u = scorer.potential_energy(f1, [f1, f2])
    assert abs(u - (-1.0)) < 1e-5

def test_write_physics_to_graph_batching():
    config = Config()
    config.data["quantum_gravity_constant"] = 1.0
    config.data["repulsive_constant"] = 0.05

    class SpyIndexer:
        def __init__(self):
            self.queries = []
        def query_graph(self, cypher):
            self.queries.append(cypher)
            return []

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

    # We expect 2 query calls instead of 6 calls (3 node updates + 3 edge updates)
    assert len(indexer.queries) <= 2
    # Check that query contains update statement elements
    assert "MATCH (f0:Function)" in indexer.queries[0]
    assert "f0.mass =" in indexer.queries[0]

