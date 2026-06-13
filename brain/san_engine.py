from enum import Enum
from typing import Dict, List, Any, Optional
import time

class BeliefState(str, Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    REJECTED = "REJECTED"
    SUPERPOSITION = "SUPERPOSITION"

class SANEngine:
    def __init__(self, min_entropy: float = 0.01, collapse_threshold: float = 0.8, gap_threshold: float = 0.2, observation_window: int = 3):
        self.min_entropy = min_entropy
        self.collapse_threshold = collapse_threshold
        self.gap_threshold = gap_threshold
        self.observation_window = observation_window
        self.symbols: Dict[str, Dict[str, Any]] = {}
        self.archetypes = ["Gate", "Sink", "Transform", "IO", "Storage"]

    def _init_symbol(self, symbol: str):
        if symbol not in self.symbols:
            initial_prob = 1.0 / len(self.archetypes)
            self.symbols[symbol] = {
                "beliefs": {a: initial_prob for a in self.archetypes},
                "timeline": [],
                "status": BeliefState.SUPERPOSITION,
                "observation_count": 0,
                "winner": None,
                "support_mass": 0
            }

    def update_belief(self, symbol: str, archetype: str, weight: float, trust: float = 0.5):
        self._init_symbol(symbol)
        state = self.symbols[symbol]
        
        likelihood_base = trust * weight
        
        for a in self.archetypes:
            if a == archetype:
                state["beliefs"][a] *= (1.0 + likelihood_base)
            else:
                state["beliefs"][a] *= (1.0 - likelihood_base * 0.5)
        
        # Robust normalization with floor
        self._normalize_beliefs(state)
        
        state["timeline"].append({
            "timestamp": time.time(),
            "beliefs": state["beliefs"].copy()
        })
        
        state["observation_count"] += 1
        state["support_mass"] += trust
        
        self._check_collapse(symbol)

    def _normalize_beliefs(self, state: Dict[str, Any]):
        beliefs = state["beliefs"]
        total = sum(beliefs.values())
        
        # Preliminary normalize
        for a in self.archetypes:
            beliefs[a] /= total

        # Apply floor and redistribute excess
        floored = {a: False for a in self.archetypes}
        for a in self.archetypes:
            if beliefs[a] < self.min_entropy:
                beliefs[a] = self.min_entropy
                floored[a] = True
        
        # Re-distribute to non-floored
        while True:
            total = sum(beliefs.values())
            if abs(total - 1.0) < 1e-9:
                break
                
            non_floored = [a for a, f in floored.items() if not f]
            if not non_floored: # All floored?
                # Just divide equally
                for a in self.archetypes:
                    beliefs[a] = 1.0 / len(self.archetypes)
                break
                
            excess = total - 1.0
            # Distribute excess proportionally among non-floored
            sub_total = sum(beliefs[a] for a in non_floored)
            for a in non_floored:
                beliefs[a] -= excess * (beliefs[a] / sub_total)
                
            # Check if any new ones dipped below floor
            newly_floored = False
            for a in non_floored:
                if beliefs[a] < self.min_entropy:
                    beliefs[a] = self.min_entropy
                    floored[a] = True
                    newly_floored = True
            
            if not newly_floored:
                # Final normalization for precision
                f_total = sum(beliefs.values())
                for a in self.archetypes:
                    beliefs[a] /= f_total
                break

    def _check_collapse(self, symbol: str):
        state = self.symbols[symbol]
        if state["observation_count"] < self.observation_window:
            return

        sorted_beliefs = sorted(state["beliefs"].items(), key=lambda x: x[1], reverse=True)
        winner, win_prob = sorted_beliefs[0]
        runner_up, run_prob = sorted_beliefs[1]
        
        if win_prob > self.collapse_threshold and (win_prob - run_prob) > self.gap_threshold:
            state["status"] = BeliefState.ACTIVE
            state["winner"] = winner
        else:
            state["status"] = BeliefState.SUPERPOSITION
            state["winner"] = None

    def get_belief_state(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.symbols.get(symbol)
