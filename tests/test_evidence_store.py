import pytest
import os
import json
from brain.evidence_store import EvidenceStore

def test_add_observation(tmp_path):
    store_file = os.path.join(tmp_path, "evidence.jsonl")
    store = EvidenceStore(store_file)
    
    obs_id = store.add_observation(
        fact="Function X writes to balance field",
        source="AST",
        obs_type="mutation",
        scope="execution",
        trust=0.7
    )
    
    assert obs_id is not None
    obs = store.get_observation(obs_id)
    assert obs["fact"] == "Function X writes to balance field"
    assert obs["source"] == "AST"
    assert obs["trust"] == 0.7

def test_evidence_lineage(tmp_path):
    store_file = os.path.join(tmp_path, "evidence.jsonl")
    store = EvidenceStore(store_file)
    
    parent_id = store.add_observation(fact="Raw AST node", source="AST")
    child_id = store.add_observation(
        fact="Derived behavior atom", 
        source="CEM",
        parent_id=parent_id
    )
    
    child = store.get_observation(child_id)
    assert child["parent_id"] == parent_id
    
    lineage = store.get_lineage(child_id)
    assert parent_id in lineage

def test_supersession(tmp_path):
    store_file = os.path.join(tmp_path, "evidence.jsonl")
    store = EvidenceStore(store_file)
    
    old_id = store.add_observation(fact="Balance is updated", source="AST")
    new_id = store.add_observation(
        fact="Balance is incremented", 
        source="AST",
        supersedes=old_id
    )
    
    old_obs = store.get_observation(old_id)
    assert old_obs["status"] == "superseded"
    assert old_obs["superseded_by"] == new_id
