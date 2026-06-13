import pytest
from brain.cognitive_layer import CognitiveLayer

def test_activation_energy():
    layer = CognitiveLayer()
    
    # Similarity=0.8, Mass=10, PE=0.5, Uncertainty=0.5, Recency=1.0
    activation = layer.calculate_activation(
        similarity=0.8,
        mass=10.0,
        potential_energy=-5.0, # abs(-5.0) = 5.0
        uncertainty=0.5,
        recency=1.0
    )
    
    # 0.8 * log(11) * 5 * 0.5 * 1.0
    import math
    expected = 0.8 * math.log(11) * 5.0 * 0.5 * 1.0
    assert pytest.approx(activation, rel=1e-3) == expected

def test_attention_debt():
    layer = CognitiveLayer()
    
    # Mass=50, Uncertainty=0.8, Churn=0.9, Resolved=0.2
    debt = layer.calculate_debt(
        mass=50.0,
        uncertainty=0.8,
        churn=0.9,
        resolved_understanding=0.2,
        repo_avg_debt=10.0
    )
    
    # ((50 * 0.8 * 0.9) - 0.2) / 10.0 = (36 - 0.2) / 10 = 35.8 / 10 = 3.58
    assert pytest.approx(debt, rel=1e-3) == 3.58

def test_concept_drift():
    layer = CognitiveLayer()
    
    # Behavior=0.4, Caller=0.2, Semantic=0.8, DataFlow=0.1
    # Trigger if > 0.3
    # (0.5 * 0.4) + (0.25 * 0.2) + (0.15 * 0.8) + (0.10 * 0.1)
    # 0.2 + 0.05 + 0.12 + 0.01 = 0.38
    drift, triggers = layer.detect_drift(
        behavior_change=0.4,
        caller_change=0.2,
        semantic_change=0.8,
        data_flow_change=0.1
    )
    
    assert drift == 0.38
    assert triggers is True
