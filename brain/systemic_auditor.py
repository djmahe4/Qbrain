import re
from typing import List, Dict, Any, Set, Tuple
from brain.logger import get_logger

logger = get_logger(__name__)

def parse_signature_params(sig: str) -> List[str]:
    """
    Extracts parameter names from a function/method signature.
    E.g. '($key, $response)' -> ['$key', '$response']
    """
    if not sig:
        return []
    sig = sig.strip()
    if sig.startswith('(') and sig.endswith(')'):
        sig = sig[1:-1]
    
    parts = []
    current = []
    depth = 0
    in_str = False
    str_char = None
    escaped = False
    for char in sig:
        if escaped:
            escaped = False
            current.append(char)
            continue
        if char == '\\':
            escaped = True
            current.append(char)
            continue
        if in_str:
            if char == str_char:
                in_str = False
            current.append(char)
            continue
        if char in ('"', "'", "`"):
            in_str = True
            str_char = char
            current.append(char)
            continue
        if char in ('(', '[', '{'):
            depth += 1
        elif char in (')', ']', '}'):
            depth -= 1
        elif char == ',' and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current).strip())
        
    params = []
    for p in parts:
        # Match variable pattern starting with $ for PHP, or default to the last word
        match = re.search(r'\$[a-zA-Z_\x7f-\xff][a-zA-Z0-9_\x7f-\xff]*', p)
        if match:
            params.append(match.group(0))
        else:
            # Fallback for other languages (get the parameter name)
            words = p.split('=')[0].split()
            if words:
                params.append(words[-1])
    return params

def parse_arguments_list(args_str: str) -> List[str]:
    """
    Splits arguments passed to a function call by comma, ignoring nested commas inside strings/parens.
    E.g. "$key, htmlspecialchars($user)" -> ["$key", "htmlspecialchars($user)"]
    """
    if not args_str:
        return []
    parts = []
    current = []
    depth = 0
    in_str = False
    str_char = None
    escaped = False
    for char in args_str:
        if escaped:
            escaped = False
            current.append(char)
            continue
        if char == '\\':
            escaped = True
            current.append(char)
            continue
        if in_str:
            if char == str_char:
                in_str = False
            current.append(char)
            continue
        if char in ('"', "'", "`"):
            in_str = True
            str_char = char
            current.append(char)
            continue
        if char in ('(', '[', '{'):
            depth += 1
        elif char in (')', ']', '}'):
            depth -= 1
        elif char == ',' and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts

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
                # state is a dict: {"state": "TAINTED", "type": ..., ...}
                if isinstance(state, dict) and state.get("state") == "TAINTED":
                    new_tainted.add(var)
            
            # 2. Check for Sinks (Terminal Points)
            # If any tainted variable (inherited or local) reaches a dangerous sink
            all_tainted = tainted_vars.union(new_tainted)
            
            dangerous_sinks = ["echo", "print", "query", "exec", "system", "shell_exec", "eval", "include", "require", "file_get_contents", "header", "setcookie"]
            
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
                callee_obj = self.func_lookup.get(callee)
                callee_params = []
                if callee_obj:
                    callee_params = parse_signature_params(callee_obj.get("signature", ""))
                
                for flow in local_flow:
                    if flow.get("sink") and (flow["sink"] in callee or callee in flow["sink"]):
                        if flow.get("variable") in all_tainted:
                            # Map caller variable to callee parameter name by position
                            args_str = flow.get("args", "")
                            args_list = parse_arguments_list(args_str)
                            try:
                                idx = -1
                                for i, arg_expr in enumerate(args_list):
                                    escaped_var = re.escape(flow["variable"])
                                    pattern = fr"(?<![\w\$]){escaped_var}(?![\w\$])"
                                    if re.search(pattern, arg_expr):
                                        idx = i
                                        break
                                if idx != -1 and idx < len(callee_params):
                                    passed_to_callee.add(callee_params[idx])
                                else:
                                    if callee_params:
                                        passed_to_callee.add(callee_params[min(idx if idx != -1 else 0, len(callee_params)-1)])
                                    else:
                                        # No parameter metadata, pass the caller variable name as fallback
                                        passed_to_callee.add(flow["variable"])
                            except Exception:
                                passed_to_callee.add(flow["variable"])
                
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
