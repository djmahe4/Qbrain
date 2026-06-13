import hashlib
from enum import Enum
from typing import Dict, List, Any, Optional, Set

class AtomType(str, Enum):
    CONTROL = "CONTROL"
    STATE_CHANGE = "STATE_CHANGE"
    STATE_BOUNDARY = "STATE_BOUNDARY"
    EXTERNAL = "EXTERNAL"
    COMPENSATION = "COMPENSATION"
    SIDE_EFFECT = "SIDE_EFFECT"

class TransitionType(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SIDE_EFFECT = "SIDE_EFFECT"
    COMPENSATION = "COMPENSATION"

class CEMEngine:
    def __init__(self):
        self.atoms: Dict[str, Dict[str, Any]] = {}
        self.transitions: List[Dict[str, Any]] = []

    def create_atom(self, name: str, atom_type: AtomType, behavior_hash: str, flow_signature: str) -> str:
        # Identity Persistence: Atoms use stable IDs based on behavior_hash + flow_signature
        atom_id = hashlib.sha256(f"{behavior_hash}{flow_signature}".encode()).hexdigest()
        
        self.atoms[atom_id] = {
            "id": atom_id,
            "name": name,
            "type": atom_type,
            "behavior_hash": behavior_hash,
            "flow_signature": flow_signature
        }
        return atom_id

    def get_atom(self, atom_id: str) -> Optional[Dict[str, Any]]:
        return self.atoms.get(atom_id)

    def add_transition(self, from_id: str, to_id: str, trans_type: TransitionType, confidence: float = 0.5):
        self.transitions.append({
            "from": from_id,
            "to": to_id,
            "type": trans_type,
            "confidence": confidence
        })

    def predict_impact(self, start_atom_id: str) -> Dict[str, List[str]]:
        impact = {
            "direct": [],
            "secondary": [],
            "tertiary": []
        }
        
        # Simple graph traversal for blast radius
        visited = set()
        
        # Direct
        direct_targets = [t["to"] for t in self.transitions if t["from"] == start_atom_id]
        impact["direct"] = direct_targets
        visited.add(start_atom_id)
        visited.update(direct_targets)
        
        # Secondary
        secondary_targets = []
        for d in direct_targets:
            targets = [t["to"] for t in self.transitions if t["from"] == d and t["to"] not in visited]
            secondary_targets.extend(targets)
        
        impact["secondary"] = list(set(secondary_targets))
        visited.update(secondary_targets)
        
        # Tertiary (Mocking graph-based message passing for now as per plan)
        tertiary_targets = []
        for s in secondary_targets:
            targets = [t["to"] for t in self.transitions if t["from"] == s and t["to"] not in visited]
            tertiary_targets.extend(targets)
        
        impact["tertiary"] = list(set(tertiary_targets))
        
        return impact
