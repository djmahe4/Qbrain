import re
from typing import List, Dict, Any, Set, Tuple
from brain.logger import get_logger

logger = get_logger(__name__)

class SystemicAuditor:
    """
    Connects microscopic local dataflows into macroscopic systemic chains.
    Identifies reachable sinks from tainted sources across function boundaries.
    """
    def __init__(self, indexer, calls_map: Dict[str, Dict], funcs: List[Dict[str, Any]]):
        self.indexer = indexer
        self.calls_map = calls_map
        self.funcs = funcs
        self.func_lookup = {f["name"]: f for f in funcs}

    def trace_taint_propagation(self, start_func: str) -> List[Dict[str, Any]]:
        """
        Traces how a TAINTED state propagates from a starting function/script.
        """
        findings = []
        visited = set()
        # queue stores (func_name, current_tainted_vars, path_taken)
        queue = [(start_func, set(), [start_func])]
        
        while queue:
            curr_name, tainted_vars, path = queue.pop(0)
            if curr_name in visited:
                continue
            visited.add(curr_name)
            
            f_obj = self.func_lookup.get(curr_name)
            if not f_obj:
                continue
                
            local_flow = f_obj.get("flow_paths", [])
            local_states = f_obj.get("variable_states", {})
            
            # 1. Identify new tainted variables in this function
            new_tainted = set()
            for var, state in local_states.items():
                if state == "TAINTED":
                    new_tainted.add(var)
            
            # 2. Check for Sinks (Terminal Points)
            # If any tainted variable (inherited or local) reaches a dangerous sink
            all_tainted = tainted_vars.union(new_tainted)
            
            dangerous_sinks = ["echo", "print", "query", "exec", "system", "shell_exec", "eval"]
            
            for flow in local_flow:
                if flow.get("variable") in all_tainted:
                    sink = flow.get("sink", "").lower()
                    # Check if sink is dangerous
                    if any(ds in sink for ds in dangerous_sinks):
                        findings.append({
                            "type": "Global Dataflow Vulnerability",
                            "path": " -> ".join(path),
                            "variable": flow["variable"],
                            "sink": flow["sink"],
                            "state": flow["state"],
                            "severity": "CRITICAL" if flow["state"] == "TAINTED" else "HIGH"
                        })
            
            # 3. Propagate to callees
            callees = self.calls_map.get(curr_name, {}).get("callees", [])
            for callee in callees:
                # Find which variables are passed to this callee
                passed_to_callee = set()
                for flow in local_flow:
                    if flow.get("sink") and (flow["sink"] in callee or callee in flow["sink"]):
                        if flow.get("variable") in all_tainted:
                            passed_to_callee.add(flow["variable"])
                
                # In macroscopic view, we assume if we pass a tainted var, the callee becomes tainted
                if callee not in visited:
                    queue.append((callee, passed_to_callee, path + [callee]))
                    
        return findings

    def audit_all_entrypoints(self, entrypoints: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        all_findings = []
        for ep in entrypoints:
            ep_name = ep.get("name") or ep.get("file")
            if ep_name:
                logger.info(f"Tracing systemic dataflow from entrypoint: {ep_name}")
                findings = self.trace_taint_propagation(ep_name)
                all_findings.extend(findings)
        return all_findings
