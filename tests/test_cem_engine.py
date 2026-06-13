import pytest
from brain.cem_engine import CEMEngine, AtomType, TransitionType

def test_atom_creation():
    engine = CEMEngine()
    atom_id = engine.create_atom(
        name="update_balance",
        atom_type=AtomType.STATE_CHANGE,
        behavior_hash="h1",
        flow_signature="s1"
    )
    
    assert atom_id is not None
    atom = engine.get_atom(atom_id)
    assert atom["name"] == "update_balance"
    assert atom["type"] == AtomType.STATE_CHANGE

def test_transition_mapping():
    engine = CEMEngine()
    a1 = engine.create_atom("validate", AtomType.STATE_BOUNDARY, "h1", "s1")
    a2 = engine.create_atom("charge", AtomType.EXTERNAL, "h2", "s2")
    
    engine.add_transition(a1, a2, TransitionType.SUCCESS, confidence=0.9)
    
    impact = engine.predict_impact(a1)
    assert a2 in impact["direct"]

def test_blast_radius():
    engine = CEMEngine()
    a1 = engine.create_atom("auth", AtomType.STATE_BOUNDARY, "h1", "s1")
    a2 = engine.create_atom("process", AtomType.STATE_CHANGE, "h2", "s2")
    a3 = engine.create_atom("log", AtomType.SIDE_EFFECT, "h3", "s3")
    
    engine.add_transition(a1, a2, TransitionType.SUCCESS)
    engine.add_transition(a2, a3, TransitionType.SIDE_EFFECT)
    
    impact = engine.predict_impact(a1)
    assert a2 in impact["direct"]
    assert a3 in impact["secondary"]
