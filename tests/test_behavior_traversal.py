import pytest
from unittest.mock import MagicMock
from brain.librarian import LibrarianEngine

def test_behavior_traversal_state_limit():
    """
    Test that behavior traversal respects a maximum state limit.
    """
    engine = LibrarianEngine(".", ".")
    
    # Mock calls_map with many callees
    calls_map = {
        "root": {"callees": ["c1", "c2", "c3", "c4", "c5", "c6", "c7"]},
        "c1": {"callees": []},
        "c2": {"callees": []},
        "c3": {"callees": []},
        "c4": {"callees": []},
        "c5": {"callees": []},
        "c6": {"callees": []},
        "c7": {"callees": []},
    }
    
    # Generate model with max_states = 4
    # The entrypoint 'root' is the first state, so it should only pick up 3 more callees
    res = engine.generate_behavior_model(
        entrypoint_func="root",
        entrypoint_path="root.php",
        calls_map=calls_map,
        funcs=[],
        sym_meta={},
        max_depth=10,
        max_states=4
    )
    
    assert len(res["states"]) == 4
    assert "root" in res["states"]

def test_make_transition_label_exact_matching():
    """
    Test that transition labels use exact matching for sinks.
    """
    engine = LibrarianEngine(".", ".")
    
    # Mock data
    funcs = [
        {
            "name": "caller",
            "flow_paths": [
                {"sink": "echo", "variable": "$data", "state": "TAINTED"},
                {"sink": "dvwaHtmlEcho", "variable": "$page", "state": "SAFE"}
            ]
        }
    ]
    
    # Case 1: Exact match for echo
    label = engine._make_transition_label("caller", "echo", funcs, {})
    assert label == "$data:TAINTED"
    
    # Case 2: Exact match for dvwaHtmlEcho
    label = engine._make_transition_label("caller", "dvwaHtmlEcho", funcs, {})
    assert label == "$page:SAFE"
    
    # Case 3: Qualified name segment match
    # If the callee is 'namespace.sub.echo', it should match the 'echo' sink
    label = engine._make_transition_label("caller", "namespace.sub.echo", funcs, {})
    assert label == "$data:TAINTED"

def test_behavior_traversal_metadata_late_binding():
    """
    Test that metadata is fetched for symbols discovered during traversal.
    """
    engine = LibrarianEngine(".", ".")
    
    calls_map = {
        "root": {"callees": ["external_func"]},
        "external_func": {"callees": []}
    }
    
    # 'external_func' is in sym_meta but not in funcs
    sym_meta = {
        "external_func": {
            "params": ["$id"],
            "returns": "void",
            "docstring": "External API",
            "variable_states": {}
        }
    }
    
    res = engine.generate_behavior_model(
        entrypoint_func="root",
        entrypoint_path="root.php",
        calls_map=calls_map,
        funcs=[], # Empty funcs
        sym_meta=sym_meta,
        max_depth=10,
        max_states=50
    )
    
    assert "external_func" in res["state_meta"]
    assert res["state_meta"]["external_func"]["docstring"] == "External API"
