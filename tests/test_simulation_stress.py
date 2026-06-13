import pytest
import time
import numpy as np
import random
from brain.quantum_scorer import QuantumScorer, FunctionNode

def test_simulation_stress_1000_nodes():
    from brain.config import Config
    from brain.indexer import Indexer
    config = Config()
    indexer = Indexer(config)
    scorer = QuantumScorer(config, indexer)
    nodes = []
    
    print("\nGenerating 1000 nodes...")
    for i in range(1000):
        emb = np.random.rand(384).astype(np.float32)
        node = FunctionNode(
            name=f"func_{i}",
            embedding=emb,
            complexity=random.uniform(1.0, 10.0),
            side_effects=random.uniform(0.0, 1.0),
            is_exported=random.choice([True, False])
        )
        # Random initial 2D positions
        node.position = [random.uniform(-10, 10), random.uniform(-10, 10)]
        nodes.append(node)
        
    start_time = time.time()
    print("Starting simulation...")
    # Run a few iterations
    scorer.run_simulation(nodes, iterations=20)
    end_time = time.time()
    
    duration = end_time - start_time
    print(f"Simulation of 1000 nodes took {duration:.2f} seconds.")
    
    # Check for basic sanity
    for node in nodes:
        assert not np.isnan(node.position[0])
        assert not np.isnan(node.position[1])
        assert node.business_score >= 0.0
        
    # We expect 1000 nodes to finish in < 30 seconds with Barnes-Hut
    # (actually should be much faster)
    assert duration < 60.0 

def test_simulation_stability():
    from brain.config import Config
    from brain.indexer import Indexer
    config = Config()
    indexer = Indexer(config)
    scorer = QuantumScorer(config, indexer)
    # 2 nodes very close
    emb = np.zeros(384)
    n1 = FunctionNode("n1", emb)
    n2 = FunctionNode("n2", emb)
    n1.position = [0.0, 0.0]
    n2.position = [1e-9, 1e-9] # Very close
    
    nodes = [n1, n2]
    # Should not crash with ZeroDivisionError
    scorer.run_simulation(nodes, iterations=5)
    
    assert not np.isnan(n1.position[0])
