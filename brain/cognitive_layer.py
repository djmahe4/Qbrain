import math
from typing import Tuple, List, Dict, Any

class CognitiveLayer:
    def __init__(self, drift_threshold: float = 0.3):
        self.drift_threshold = drift_threshold

    def calculate_activation(
        self, 
        similarity: float, 
        mass: float, 
        potential_energy: float, 
        uncertainty: float, 
        recency: float
    ) -> float:
        """
        Activation = Similarity * log(1+Mass) * abs(PotentialEnergy) * Uncertainty * Recency
        """
        return similarity * math.log(1.0 + mass) * abs(potential_energy) * uncertainty * recency

    def calculate_debt(
        self, 
        mass: float, 
        uncertainty: float, 
        churn: float, 
        resolved_understanding: float,
        repo_avg_debt: float = 1.0
    ) -> float:
        """
        Normalized Debt = ((Mass * Uncertainty * Churn) - ResolvedUnderstanding) / RepositoryAverageDebt
        """
        raw_debt = (mass * uncertainty * churn) - resolved_understanding
        return raw_debt / max(repo_avg_debt, 1e-5)

    def detect_drift(
        self, 
        behavior_change: float, 
        caller_change: float, 
        semantic_change: float, 
        data_flow_change: float
    ) -> Tuple[float, bool]:
        """
        Drift = (0.5 * behavior) + (0.25 * caller) + (0.15 * semantic) + (0.10 * data_flow)
        """
        drift = (0.5 * behavior_change) + \
                (0.25 * caller_change) + \
                (0.15 * semantic_change) + \
                (0.10 * data_flow_change)
        
        return drift, drift > self.drift_threshold

    def calculate_learning_rate(self, potential_energy: float) -> float:
        """
        PE-Weighted Plasticity: High PE code uses high learning rate.
        Maps abs(PE) to range [0.1, 0.9]
        Assuming PE is normalized or we use a sigmoid.
        """
        pe_abs = abs(potential_energy)
        # Simple linear map for now, clipped
        lr = 0.1 + (pe_abs * 0.8)
        return min(max(lr, 0.1), 0.9)

    def get_probing_actions(self, debt: float) -> List[str]:
        """
        Returns a list of autonomous probing actions based on attention debt level.
        """
        actions = []
        if debt > 5.0: # High debt threshold
            actions.extend([
                "deep_ast_scan",
                "expand_call_graph",
                "fetch_git_history",
                "request_runtime_traces"
            ])
        elif debt > 2.0: # Moderate debt
            actions.extend([
                "standard_ast_scan",
                "check_git_history"
            ])
        return actions

    def run_sleep_cycle(self, store, cem, san) -> Dict[str, Any]:
        """
        Expensive background work: evidence replay, drift calculation, atom merging.
        """
        results = {
            "replayed_observations": 0,
            "drift_detected": [],
            "merged_atoms": 0
        }
        
        # 1. Evidence Replay (Mocking for now as per plan)
        # In a real impl, this would check historical evidence against current AST
        results["replayed_observations"] = len(store.observations)
        
        # 2. Check for Drift and Contradictions
        # This is where we'd force SAN re-evaluations if drift > threshold
        
        return results
