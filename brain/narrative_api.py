from typing import Dict, Any, List, Optional
from brain.evidence_store import EvidenceStore
from brain.cem_engine import CEMEngine
from brain.san_engine import SANEngine
from brain.cognitive_layer import CognitiveLayer

class NarrativeAPI:
    def __init__(
        self, 
        store: EvidenceStore, 
        cem: CEMEngine, 
        san: SANEngine, 
        cognitive: CognitiveLayer
    ):
        self.store = store
        self.cem = cem
        self.san = san
        self.cognitive = cognitive

    def get_cognitive_snapshot(self) -> Dict[str, Any]:
        """
        Creates an immutable snapshot of the current mind state.
        In a real impl, this might copy data to prevent race conditions during query.
        """
        snapshot = {
            "symbols": self.san.symbols.copy(),
            "atoms": self.cem.atoms.copy(),
            "transitions": self.cem.transitions.copy(),
            "version": self.store.inference_version
        }
        return snapshot

    def get_context_for_symbol(self, symbol_name: str) -> Dict[str, Any]:
        """
        Retrieves augmented context for the SLM agent.
        """
        belief_state = self.san.get_belief_state(symbol_name)
        if not belief_state:
            return {"error": "Symbol not found in cognitive model"}
            
        # Build causal paths from CEM
        # Find atom for this symbol (heuristic: name match)
        atom_id = None
        for aid, atom in self.cem.atoms.items():
            if atom["name"] == symbol_name:
                atom_id = aid
                break
        
        causal_paths = self.cem.predict_impact(atom_id) if atom_id else {}
        
        # Get evidence from store
        # In a real impl, SAN would store IDs of observations
        # For now, we'll return generic metadata
        
        context = {
            "symbol": symbol_name,
            "beliefs": belief_state["beliefs"],
            "status": belief_state["status"],
            "winner": belief_state["winner"],
            "support_mass": belief_state["support_mass"],
            "causal_paths": causal_paths,
            "uncertainty": 1.0 - (max(belief_state["beliefs"].values()) if belief_state["beliefs"] else 0.0)
        }
        
        return context

    def generate_prose_summary(self, symbol_name: str) -> str:
        """
        Helper to turn cognitive state into high-level summary for the user.
        """
        ctx = self.get_context_for_symbol(symbol_name)
        if "error" in ctx:
            return f"The brain has no knowledge of {symbol_name}."
            
        summary = f"Symbol '{symbol_name}' is currently perceived as a {ctx['winner'] or 'Superposition'}.\n"
        summary += f"Confidence in this interpretation is {1.0 - ctx['uncertainty']:.2f}.\n"
        
        if ctx["causal_paths"].get("direct"):
            summary += f"Directly impacts: {', '.join(ctx['causal_paths']['direct'])}.\n"
            
        return summary
