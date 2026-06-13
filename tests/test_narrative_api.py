import pytest
from brain.narrative_api import NarrativeAPI
from brain.evidence_store import EvidenceStore
from brain.cem_engine import CEMEngine
from brain.san_engine import SANEngine
from brain.cognitive_layer import CognitiveLayer

def test_narrative_context(tmp_path):
    store = EvidenceStore(str(tmp_path / "evidence.jsonl"))
    cem = CEMEngine()
    san = SANEngine()
    cognitive = CognitiveLayer()
    
    api = NarrativeAPI(store, cem, san, cognitive)
    
    # Mock some data
    san.update_belief("auth", "Gate", 1.0, trust=1.0)
    san.update_belief("auth", "Gate", 1.0, trust=1.0)
    san.update_belief("auth", "Gate", 1.0, trust=1.0)
    
    snapshot = api.get_cognitive_snapshot()
    assert "auth" in snapshot["symbols"]
    assert snapshot["symbols"]["auth"]["winner"] == "Gate"

def test_narrative_explanation(tmp_path):
    store = EvidenceStore(str(tmp_path / "evidence.jsonl"))
    cem = CEMEngine()
    san = SANEngine()
    cognitive = CognitiveLayer()
    
    api = NarrativeAPI(store, cem, san, cognitive)
    
    obs_id = store.add_observation("Always checks session", "Manual", trust=1.0)
    san.update_belief("auth", "Gate", 1.0, trust=1.0) # This should link to evidence in a real impl
    
    # We'll just verify the API returns structured data for the SLM to consume
    context = api.get_context_for_symbol("auth")
    assert context["beliefs"]["Gate"] >= 0.5
