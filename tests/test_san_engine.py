import pytest
from brain.san_engine import SANEngine, BeliefState

def test_belief_update():
    engine = SANEngine()
    symbol = "process_payment"
    
    # Update with some evidence
    engine.update_belief(symbol, "Sink", 1.0, trust=0.9)
    
    state = engine.get_belief_state(symbol)
    assert state["beliefs"]["Sink"] > 0.3 # Initial was 0.2
    assert "Sink" in state["timeline"][0]["beliefs"]

def test_belief_competition():
    engine = SANEngine()
    symbol = "validate_user"
    
    # Multiple strong evidence for Gate should suppress others
    for _ in range(5):
        engine.update_belief(symbol, "Gate", 1.0, trust=1.0)
    
    state = engine.get_belief_state(symbol)
    assert state["beliefs"]["Gate"] > 0.8
    # Uncertainty floor: others should not be zero
    assert all(p >= 0.01 for p in state["beliefs"].values())

def test_temporal_consolidation():
    engine = SANEngine()
    symbol = "auth"
    
    # 3 observations needed for collapse
    for _ in range(2):
        engine.update_belief(symbol, "Gate", 1.0, trust=1.0)
    
    state = engine.get_belief_state(symbol)
    assert state["status"] == BeliefState.SUPERPOSITION
    
    engine.update_belief(symbol, "Gate", 1.0, trust=1.0)
    state = engine.get_belief_state(symbol)
    assert state["status"] == BeliefState.ACTIVE
    assert state["winner"] == "Gate"
