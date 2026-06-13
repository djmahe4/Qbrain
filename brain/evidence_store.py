import os
import json
import hashlib
import time
from typing import Any, Dict, List, Optional

class EvidenceStore:
    def __init__(self, storage_path: str, inference_version: str = "1.0.0", policy_version: str = "1.0.0"):
        self.storage_path = storage_path
        self.inference_version = inference_version
        self.policy_version = policy_version
        self.observations: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    obs = json.loads(line)
                    self.observations[obs["id"]] = obs

    def _save_observation(self, obs: Dict[str, Any]):
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obs) + "\n")

    def add_observation(
        self, 
        fact: str, 
        source: str, 
        obs_type: str = "generic", 
        scope: str = "semantic", 
        trust: float = 0.5,
        parent_id: Optional[str] = None,
        supersedes: Optional[str] = None
    ) -> str:
        timestamp = time.time()
        obs_id = hashlib.sha256(f"{fact}{source}{timestamp}".encode()).hexdigest()
        
        obs = {
            "id": obs_id,
            "fact": fact,
            "source": source,
            "type": obs_type,
            "scope": scope,
            "trust": trust,
            "timestamp": timestamp,
            "parent_id": parent_id,
            "status": "active",
            "inference_version": self.inference_version,
            "policy_version": self.policy_version
        }
        
        if supersedes:
            if supersedes in self.observations:
                self.observations[supersedes]["status"] = "superseded"
                self.observations[supersedes]["superseded_by"] = obs_id
                # Note: In a real append-only ledger, we'd append a 'superseded' event instead of mutating.
                # For this implementation, we update in-memory and the file is technically append-only for new obs.
                # Re-saving the entire state for a small project is acceptable or we can use a more robust DB.
                self._rewrite_store()
        
        self.observations[obs_id] = obs
        self._save_observation(obs)
        return obs_id

    def _rewrite_store(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            for obs in self.observations.values():
                f.write(json.dumps(obs) + "\n")

    def get_observation(self, obs_id: str) -> Optional[Dict[str, Any]]:
        return self.observations.get(obs_id)

    def get_lineage(self, obs_id: str) -> List[str]:
        lineage = []
        current_id = obs_id
        while current_id:
            obs = self.get_observation(current_id)
            if obs and obs.get("parent_id"):
                lineage.append(obs["parent_id"])
                current_id = obs["parent_id"]
            else:
                break
        return lineage
