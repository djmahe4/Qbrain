import os
import datetime
import yaml
import json
import time
import re
import hashlib
from collections import deque
from typing import Dict, Any, List, Optional, Set
from contextlib import contextmanager
from brain.logger import get_logger

logger = get_logger(__name__)

class LibrarianEngine:
    """
    Knowledge synchronizer between the memory graph and Obsidian vault.
    Restored and enhanced for Scenario-Driven mapping.
    """
    def __init__(self, repo_path: str, vault_path: str, indexer=None):
        self.repo_path = os.path.abspath(repo_path)
        self.vault_path = os.path.abspath(vault_path)
        self.indexer = indexer
        os.makedirs(self.vault_path, exist_ok=True)
        self.lock_file = os.path.join(self.repo_path, ".qbrain.lock")

    @contextmanager
    def lock(self, timeout: float = 30.0, retry_interval: float = 1.0):
        """PID-based file locking to prevent concurrent vault updates."""
        if not os.path.exists(self.vault_path):
            os.makedirs(self.vault_path, exist_ok=True)
            
        # Fail fast if lock file exists and is owned by the current process
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, "r") as f:
                    raw = f.read().strip()
                    if raw:
                        try:
                            data = json.loads(raw)
                            lock_pid = data.get("pid")
                        except json.JSONDecodeError:
                            lock_pid = int(raw)
                        if lock_pid == os.getpid():
                            raise RuntimeError("Failed to acquire lock: locked by a running process")
            except RuntimeError:
                raise
            except Exception:
                pass

        start_time = time.time()
        acquired = False
        while time.time() - start_time < timeout:
            try:
                # Try to create lock file atomically
                with open(self.lock_file, "x") as f:
                    lock_data = {
                        "pid": os.getpid(),
                        "create_time": time.time()
                    }
                    f.write(json.dumps(lock_data))
                acquired = True
                break
            except FileExistsError:
                # Check if lock is stale
                if self._is_lock_stale():
                    self._force_release_lock()
                    continue
                time.sleep(retry_interval)
        
        if not acquired:
            raise RuntimeError("Failed to acquire lock: locked by a running process")
            
        try:
            yield
        finally:
            self._force_release_lock()

    def _is_lock_stale(self) -> bool:
        if not os.path.exists(self.lock_file):
            return True
        try:
            with open(self.lock_file, "r") as f:
                raw = f.read().strip()
                if not raw:
                    return True
                
                pid = None
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        pid = data.get("pid")
                except Exception:
                    pass
                
                if pid is None:
                    try:
                        pid = int(raw)
                    except ValueError:
                        return True
            
            if pid == os.getpid():
                return False
            
            if os.name == "nt":
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                kernel32 = ctypes.windll.kernel32
                kernel32.OpenProcess.restype = ctypes.c_void_p
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if handle:
                    kernel32.CloseHandle(ctypes.c_void_p(handle))
                    return False
                err = kernel32.GetLastError()
                if err == 5: return False
                return True
            else:
                try:
                    os.kill(pid, 0)
                    return False
                except OSError as e:
                    import errno
                    if e.errno == errno.ESRCH: return True
                    return False
        except PermissionError: return False
        except Exception: return True

    def _force_release_lock(self):
        if os.path.exists(self.lock_file):
            try: os.remove(self.lock_file)
            except Exception: pass

    def setup_vault(self):
        """Create standard vault directories."""
        dirs = [
            "symbols", "files", "behaviors", "changes", "changes/recent",
            "changes/archive", "rules", "narratives"
        ]
        for d in dirs:
            os.makedirs(os.path.join(self.vault_path, d), exist_ok=True)
        baseline_path = os.path.join(self.vault_path, "baseline.md")
        if not os.path.exists(baseline_path):
            with open(baseline_path, "w", encoding="utf-8") as f:
                f.write("# Qbrain Baseline\n")

    def _get_safe_filename(self, name: str) -> str:
        """Standardized safe naming for all exported entities."""
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
        if len(safe) > 60:
            h = hashlib.md5(name.encode()).hexdigest()[:6]
            return f"{safe[:50]}_{h}"
        return safe

    def _sanitize_for_table(self, text: str) -> str:
        """Sanitizes text for use in a markdown table cell and mermaid nodes."""
        if not text: return "—"
        # Remove newlines and pipe characters
        clean = str(text).replace("\n", " ").replace("\r", "").replace("|", "\\|").replace('"', "'")
        # Limit length to prevent "hallucinations" of large code blocks
        if len(clean) > 80: clean = clean[:77] + "..."
        return clean

    def _get_semantic_state_label(self, state: str) -> str:
        """Translates technical/raw states into semantic labels."""
        if not state: return "unknown"
        
        m_inc_req = re.match(r"^\[(include|require)(_once)?\]\s*(.*)$", state, re.IGNORECASE)
        if m_inc_req:
            verb, once, path = m_inc_req.groups()
            suffix = " (once)" if once else ""
            return f"{verb.capitalize()}{suffix}: {path}"
        if state.startswith("Redirect:"):
            return state
        sinks = {
            "echo": "Render Output",
            "print": "Log/Display",
            "die": "Terminate",
            "header": "HTTP Redirect",
            "mysqli_query": "[(DB)] Query",
            "mysqli_prepare": "[(DB)] Prepare",
            "mysqli_connect": "[(DB)] Connect",
            "eval": "🚨 DANGEROUS: Dynamic Eval",
            "exec": "🚨 DANGEROUS: System Exec",
            "system": "🚨 DANGEROUS: System Call",
            "shell_exec": "🚨 DANGEROUS: Shell Exec"
        }
        
        for sink, label in sinks.items():
            if state.startswith(f"[{sink}]"):
                content = state.replace(f"[{sink}]", "").strip()
                return f"{label}: {content[:60]}..." if len(content) > 60 else f"{label}: {content}"
            if state == sink:
                return label

        return state.split("/")[-1] if "/" in state else state

    def _safe_path(self, subdir: str, filename: str) -> str:
        """Sanitize path and ensure it's inside the vault."""
        target = os.path.abspath(os.path.join(self.vault_path, subdir, filename))
        if not target.startswith(self.vault_path):
            raise ValueError(f"Security Risk: Path traversal detected: {target}")
        return target

    def export_symbol(self, symbol_data: dict):
        name = symbol_data.get("name")
        if not name: return
        if ".." in name or name.startswith("/") or name.startswith("\\"):
            raise ValueError(f"Security Risk: Path traversal detected in symbol name: {name}")
        # If qualified, extract short name for display
        display_name = name.split(":")[-1] if ":" in name else name
        safe_name = self._get_safe_filename(name)
        filepath = self._safe_path("symbols", f"{safe_name}.md")
        kind = symbol_data.get("kind", "Function")
        
        frontmatter = {
            "type": "symbol",
            "kind": kind,
            "name": name,
            "language": symbol_data.get("language"),
            "file": symbol_data.get("file"),
            "signature": symbol_data.get("signature"),
            "mass": symbol_data.get("mass"),
            "potential_energy": symbol_data.get("potential_energy"),
            "archetype": symbol_data.get("archetype"),
            "line": symbol_data.get("line"),
            "line_range": symbol_data.get("line_range")
        }
        
        badge = "🔧"
        if kind == "Class": badge = "🏛️"
        elif kind == "Interface": badge = "📑"
        elif kind == "Enum": badge = "🗳️"
        elif kind == "Variable": badge = "📌"
        elif kind == "Module": badge = "📦"
        elif kind == "Method": badge = "⚡"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(frontmatter, f, default_flow_style=False)
            f.write("---\n\n")
            f.write(f"# {badge} {kind}: {display_name}\n\n")
            if symbol_data.get("line") is not None:
                f.write(f"**Line:** {symbol_data.get('line')}\n\n")
            if symbol_data.get("docstring"):
                f.write(f"## Documentation\n{symbol_data.get('docstring')}\n\n")
            
            var_states = symbol_data.get("variable_states", {})
            flow_paths = symbol_data.get("flow_paths", [])
            
            # Members section for Classes and Enums
            if kind in ("Class", "Enum", "Interface"):
                f.write("## Members\n")
                # Try both qualified and display name
                symbol_meta = var_states.get(name) or var_states.get(display_name)
                methods = symbol_meta.get("methods", []) if isinstance(symbol_meta, dict) else []
                if methods:
                    f.write("### Methods\n")
                    for m in methods:
                        f.write(f"- [[{self._get_safe_filename(name + ':' + m)}|{m}]] \n")
                    f.write("\n")

                # Extract properties
                props = symbol_meta.get("properties", {}) if isinstance(symbol_meta, dict) else {}
                if props:
                    f.write("### Properties\n")
                    f.write("| Property | Type | Visibility | Default |\n")
                    f.write("|:---|:---|:---|:---|\n")
                    for p_name, p_info in props.items():
                        f.write(f"| `${p_name}` | `{p_info.get('type', 'unknown')}` | {p_info.get('visibility', '—')} | `{p_info.get('default', '—')}` |\n")
                    f.write("\n")

            if var_states:
                f.write("## Data Model & Constraints\n")
                f.write("| Variable | Type | State | Properties / Constraints |\n")
                f.write("|:---|:---|:---|:---|\n")
                for var, data in var_states.items():
                    if var == name: continue # Skip the class definition itself here
                    state = data.get("state", "CONSTANT")
                    vtype = data.get("type", "unknown")
                    details = []
                    
                    if state == "CONSTANT" and data.get("value"):
                        val = data.get("value")
                        source = data.get("source", "internal")
                        details.append(f"value `{val}` (from `{source}`)")
                    
                    props = data.get("properties", {})
                    if isinstance(props, dict):
                        for p, pdata in props.items():
                            details.append(f"prop `{p}` ({pdata.get('type')})")
                    
                    constraints = data.get("constraints", [])
                    if isinstance(constraints, list):
                        for c in list(set(constraints)):
                            details.append(f"check `{c}`")
                            
                    details_str = ", ".join(details) if details else "—"
                    f.write(f"| `{var}` | `{vtype}` | `{state}` | {details_str} |\n")
                f.write("\n")
                
            if flow_paths:
                f.write("## Dataflow Graph\n")
                f.write("```mermaid\n")
                f.write("graph LR\n")
                for i, path in enumerate(flow_paths):
                    src = str(path.get("source", "internal")).replace('"', "'")
                    sink = str(path.get("sink", "unknown")).replace('"', "'")
                    var = str(path.get("variable", "data")).replace('"', "'")
                    state = path.get("state", "UNKNOWN")
                    vtype = path.get("type", "")
                    line = f":{path.get('line')}" if path.get("line") else ""
                    label = f"{var}{line}:{vtype} ({state})" if vtype else f"{var}{line} ({state})"
                    f.write(f'  P{i}_SRC["{src}"] -- "{label}" --> P{i}_SINK["{sink}"]\n')
                f.write("```\n\n")

            if symbol_data.get("params"):
                f.write("## Parameters\n")
                for param in symbol_data.get("params", []):
                    f.write(f"- `{param.get('name')}` ({param.get('type')}): {param.get('description', '')}\n")
                f.write("\n")
            if symbol_data.get("returns"):
                ret = symbol_data.get("returns")
                rtype = ret.get("type") if isinstance(ret, dict) else (ret if isinstance(ret, str) else "")
                f.write(f"## Returns\n`{rtype}`: {ret.get('description', '') if isinstance(ret, dict) else ''}\n\n")
            
            if symbol_data.get("semantic_neighbors"):
                f.write("## Semantic Neighbors\n")
                for neighbor, sim in symbol_data["semantic_neighbors"]:
                    f.write(f"- `[[{self._get_safe_filename(neighbor)}|{neighbor.split(':')[-1]}]]` ({sim * 100:.1f}% similarity)\n")
                f.write("\n")
            
            callers = symbol_data.get("callers", [])
            callees = symbol_data.get("callees", [])
            if callers or callees:
                f.write("## Entanglements\n")
                if callers:
                    f.write("### Inbound Callers\n")
                    for caller in callers:
                        f.write(f"- `[[{self._get_safe_filename(caller)}|{caller.split(':')[-1]}]]` \n")
                if callees:
                    f.write("### Outbound Callees\n")
                    for callee in callees:
                        f.write(f"- `[[{self._get_safe_filename(callee)}|{callee.split(':')[-1]}]]` \n")
                f.write("\n")
                
            if symbol_data.get("business_rules"):
                f.write("## Business Rules\n")
                for rule in symbol_data.get("business_rules", []):
                    f.write(f"- {rule}\n")
                f.write("\n")

            if symbol_data.get("vulnerabilities"):
                f.write("## Security Findings\n")
                for vuln in symbol_data.get("vulnerabilities", []):
                    f.write(f"- **{vuln.get('severity', 'LOW')}**: {vuln.get('message') or vuln.get('description')}\n")
                f.write("\n")

            if symbol_data.get("code_snippet"):
                f.write("## Implementation\n")
                lang = symbol_data.get("language") or "generic"
                f.write(f"```{lang}\n")
                f.write(symbol_data["code_snippet"])
                f.write("\n```\n")
    def export_file(self, file_data: dict):
        file_path = file_data.get("file_path")
        if not file_path: return
        safe_name = self._get_safe_filename(file_path)
        filepath = self._safe_path("files", f"{safe_name}.md")
        
        frontmatter = {
            "type": "file",
            "file_path": file_path,
            "language": file_data.get("language"),
            "lines_of_code": file_data.get("lines_of_code"),
            "size_bytes": file_data.get("size_bytes")
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(frontmatter, f, default_flow_style=False)
            f.write("---\n\n")
            f.write(f"# File: {file_path}\n\n")
            f.write("## Metadata\n")
            if file_data.get("language"):
                f.write(f"- **Language:** {file_data.get('language')}\n")
            if file_data.get("lines_of_code") is not None:
                f.write(f"- **Lines of Code:** {file_data.get('lines_of_code')}\n")
            if file_data.get("size_bytes") is not None:
                f.write(f"- **Size:** {file_data.get('size_bytes')} bytes\n")
            var_states = file_data.get("variable_states", {})
            if var_states:
                f.write("## File-Level Data Model\n")
                f.write("| Variable | Type | State | Properties / Constraints |\n")
                f.write("|:---|:---|:---|:---|\n")
                for var, data in var_states.items():
                    state = data.get("state", "CONSTANT")
                    vtype = data.get("type", "unknown")
                    details = []
                    
                    if state == "CONSTANT" and data.get("value"):
                        val = data.get("value")
                        source = data.get("source", "internal")
                        details.append(f"value `{val}` (from `{source}`)")
                    
                    props = data.get("properties", {})
                    if isinstance(props, dict):
                        for p, pdata in props.items():
                            details.append(f"prop `{p}` ({pdata.get('type')})")
                    
                    constraints = data.get("constraints", [])
                    if isinstance(constraints, list):
                        for c in list(set(constraints)):
                            details.append(f"check `{c}`")
                            
                    details_str = ", ".join(details) if details else "—"
                    f.write(f"| `{var}` | `{vtype}` | `{state}` | {details_str} |\n")
                f.write("\n")

            symbols_data = file_data.get("symbols_data", [])
            if symbols_data:
                f.write("## Symbols and Logic\n")
                f.write("| Symbol | Kind | Line | Signature | Description |\n")
                f.write("|:---|:---|:---|:---|:---|\n")
                for s in symbols_data:
                    name = s.get("name")
                    kind = s.get("kind", "Function")
                    line = s.get("line", "—")
                    sig = s.get("signature") or name
                    doc = (s.get("docstring") or "").split("\n")[0]
                    f.write(f"| [[{name}]] | `{kind}` | {line} | `{sig}` | {doc} |\n")
                f.write("\n")

                all_rules = []
                for s in symbols_data:
                    for rule in s.get("business_rules", []):
                        all_rules.append(f"- **{s.get('name')}**: {rule}")
                
                if all_rules:
                    f.write("## Business Logic & Requirements\n")
                    for rule in all_rules:
                        f.write(f"{rule}\n")
                    f.write("\n")

                all_flows = []
                for s in symbols_data:
                    for flow in s.get("flow_paths", []):
                        all_flows.append({
                            "source": s.get("name"),
                            "variable": flow.get("variable"),
                            "state": flow.get("state"),
                            "sink": flow.get("sink"),
                            "line": flow.get("line")
                        })
                
                if all_flows:
                    f.write("## Dataflow & Taint Summary\n")
                    f.write("| Source | Variable | State | Sink | Line |\n")
                    f.write("|:---|:---|:---|:---|:---|\n")
                    for flow in all_flows:
                        f.write(f"| `{flow['source']}` | `{flow['variable']}` | `{flow['state']}` | `{flow['sink'] or 'internal'}` | {flow.get('line', '—')} |\n")
                    f.write("\n")

            symbols = file_data.get("symbols", [])
            if symbols:
                f.write("## Navigation\n")
                for s in symbols:
                    f.write(f"- [[{s}]]\n")
                f.write("\n")

    def _make_transition_label(self, caller_name: str, callee_name: str, funcs: List[dict], sym_meta: dict) -> str:
        caller_obj = next((f for f in funcs if f.get("name") == caller_name), None)
        if caller_obj:
            passed_vars = []
            callee_base = callee_name.split(".")[-1]
            decision_drivers = []
            
            for flow in caller_obj.get("flow_paths", []):
                variable = flow.get("variable", "")
                if any(x in variable for x in ["$_COOKIE", "$_SESSION", "$_GET", "$_POST", "security"]):
                    decision_drivers.append(f"{variable}")

                sink = flow.get("sink", "")
                if sink and (sink == callee_name or sink == callee_base):
                    passed_vars.append(f"{variable}:{flow.get('state')}")
            
            if decision_drivers:
                return f"[Scenario: {', '.join(list(set(decision_drivers)))}]"
            if passed_vars:
                return ", ".join(list(set(passed_vars)))

        callee_info = sym_meta.get(callee_name, {})
        params = callee_info.get("params", [])
        returns = callee_info.get("returns", {})
        parts = []
        if params:
            p = params[0] if isinstance(params[0], dict) else {"name": str(params[0])}
            ptype = p.get("type") or ""
            pname = p.get("name") or ""
            parts.append(f"{pname}:{ptype}" if ptype else pname)
        if returns:
            rtype = returns.get("type") if isinstance(returns, dict) else (returns if isinstance(returns, str) else "")
            if rtype: parts.append(f"→{rtype}")
        return ", ".join(parts) if parts else ""

    def generate_behavior_model(self, entrypoint_func: str, entrypoint_path: str, calls_map: dict, funcs: List[dict], sym_meta: dict, scenario_constraints: List[str] = None, max_depth: int = 10, max_states: int = 50) -> dict:
        states: set = {entrypoint_func}
        transitions = []
        # Initialize queue with scenario constraints if provided to influence behavior split
        initial_condition = " AND ".join(scenario_constraints) if scenario_constraints else None
        queue = deque([(entrypoint_func, None, 0, initial_condition)]) # (current, caller, depth, condition)
        visited = set()

        while queue:
            if len(states) >= max_states: break
            current, caller, depth, condition = queue.popleft()
            
            # Resolve to fully qualified name if current is unqualified
            q_name = None
            if current in sym_meta:
                q_name = current
            else:
                for f in funcs:
                    fname = f.get("name")
                    if fname == current or fname.endswith(":" + current):
                        q_name = fname
                        break
            
            lookup_key = q_name or current
            
            if caller:
                transitions.append({
                    "from": caller,
                    "to": current,
                    "label": condition or "calls"
                })
                states.add(current)
            
            if depth < max_depth:
                if lookup_key not in visited:
                    visited.add(lookup_key)
                    detailed_next = calls_map.get(lookup_key, {}).get("callees_detailed", [])
                    if detailed_next:
                        for nc, cond in detailed_next:
                            if cond and scenario_constraints:
                                is_incompatible = False
                                for sc in scenario_constraints:
                                    sc_m = re.search(r"([\$\w\(\)\[\]'\"_-]+)\s*==\s*['\"]([\w\.-]+)['\"]", sc)
                                    cond_m = re.search(r"([\$\w\(\)\[\]'\"_-]+)\s*==\s*['\"]([\w\.-]+)['\"]", cond)
                                    if sc_m and cond_m:
                                        sc_var, sc_val = sc_m.groups()
                                        cond_var, cond_val = cond_m.groups()
                                        if sc_var == cond_var and sc_val != cond_val:
                                            is_incompatible = True
                                            break
                                if is_incompatible:
                                    continue
                            queue.append((nc, current, depth + 1, cond))
                    else:
                        for nc in calls_map.get(lookup_key, {}).get("callees", []):
                            queue.append((nc, current, depth + 1, None))

                    current_obj = next((f for f in funcs if f.get("name") == lookup_key), None)
                    if current_obj and "dataflow" in current_obj:
                        for atom in current_obj["dataflow"]:
                            if atom.get("type") in ("synthesized_call", "sink"):
                                if atom.get("type") == "synthesized_call":
                                    hint = atom.get("resolved_hint") or atom.get("raw_path")
                                    verb = atom.get("verb", "call")
                                    if verb == "redirect":
                                        synth_name = f"Redirect: {hint}"
                                    else:
                                        synth_name = f"[{verb}] {hint}"
                                else:
                                    sink_name = atom.get("sink")
                                    args = atom.get("args", "")
                                    synth_name = f"[{sink_name}] {args}"
                                queue.append((synth_name, current, depth + 1, None))
        
        is_hub = len(transitions) > 15
        return {
            "entrypoint": entrypoint_func,
            "states": list(states),
            "transitions": transitions,
            "state_meta": sym_meta,
            "is_macro_map": is_hub
        }

    def export_behavior(self, behavior_data: dict):
        print(f"DEBUG: Exporting behavior: {behavior_data.get('name')}")
        name = behavior_data.get("name")
        if not name: return
        safe_name = self._get_safe_filename(name)
        filepath = self._safe_path("behaviors", f"{safe_name}.md")
        states = behavior_data.get("states", [])
        transitions = behavior_data.get("transitions", [])
        
        frontmatter = {
            "type": "behavior",
            "name": name,
            "entrypoint": behavior_data.get("entrypoint"),
            "state_count": len(states),
            "transition_count": len(transitions)
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(frontmatter, f, default_flow_style=False)
            f.write("---\n\n")
            f.write(f"# Behavior: {name}\n\n")
            
            scenario_context = behavior_data.get("scenario_context")
            if scenario_context:
                f.write("## Assumed Environmental Context\n\n")
                f.write("This implementation assumes the following environmental constraints:\n\n")
                for ctx in scenario_context:
                    f.write(f"- `{ctx}`\n")
                f.write("\n")
                
            is_macro = behavior_data.get("is_macro_map", False)
            f.write(f"## {'Macro System Map' if is_macro else 'State Machine'}\n\n")
            
            if is_macro:
                f.write("```mermaid\ngraph TD\n")
                ep = behavior_data.get("entrypoint")
                ep_alias = self._get_safe_filename(ep)
                f.write(f'  {ep_alias}["{ep}"]:::hub\n')
                f.write("  classDef hub fill:#f96,stroke:#333,stroke-width:4px;\n")
            else:
                f.write("```mermaid\nstateDiagram-v2\n")
            
            state_aliases = {}
            for s in states:
                alias = self._get_safe_filename(s)
                if not is_macro:
                    safe_s = self._get_semantic_state_label(s).replace('"', "'")
                    if alias == safe_s: f.write(f"    {safe_s}\n")
                    else: f.write(f'    state "{safe_s}" as {alias}\n')
                state_aliases[s] = alias
                
            for t in transitions:
                frm = state_aliases.get(t["from"], t["from"])
                to = state_aliases.get(t["to"], t["to"])
                cond = t.get("label")
                if is_macro:
                    if cond:
                        safe_cond = str(cond).replace("\n", " ").replace('"', "'")
                        f.write(f'  {frm} -- "{safe_cond}" --> {to}\n')
                    else: f.write(f"  {frm} --> {to}\n")
                else:
                    if cond:
                        safe_cond = str(cond).replace("\n", " ").replace('"', "'")
                        f.write(f"    {frm} --> {to}: {safe_cond}\n")
                    else: f.write(f"    {frm} --> {to}\n")
            f.write("```\n\n")
            
            f.write("## State Context\n\n")
            f.write("| State | PE | Archetype | Params | Returns | Invariants | Summary |\n")
            f.write("| :--- | ---: | :--- | :--- | :--- | :--- | :--- |\n")
            meta = behavior_data.get("state_meta", {})
            for s in states:
                s_meta = meta.get(s, {})
                pe = s_meta.get("potential_energy", "—")
                arch = s_meta.get("archetype", "—")
                if arch == "—" and (s.startswith("[") or s.startswith("Redirect:")):
                    arch = "synthesized"
                v_states = s_meta.get("variable_states", {})
                invariants = []
                for v, vdata in v_states.items():
                    if isinstance(vdata, dict) and vdata.get("constraints"):
                        # Clean up and deduplicate constraints
                        for c in vdata["constraints"]:
                            # Heuristic: only keep short, logical-looking constraints
                            if len(c) < 100 and not any(x in c for x in ["{", "}", ";"]):
                                invariants.append(c)
                
                invariants_str = ", ".join([self._sanitize_for_table(x) for x in list(set(invariants))[:3]]) if invariants else "—"
                p = s_meta.get("params", [])
                params_str = ", ".join([str(x) for x in p]) if p else "—"
                r = s_meta.get("returns", "—")
                returns_str = f"`{r}`" if r and r != "—" else "—"
                doc = s_meta.get("docstring", "")
                display_s = self._sanitize_for_table(s.split(':')[-1])
                summary = doc.split("\n")[0][:100] if doc else "—"
                summary = self._sanitize_for_table(summary)
                f.write(f"| [[{self._get_safe_filename(s)}|{display_s}]] | {pe} | {arch} | {params_str} | {returns_str} | {invariants_str} | {summary} |\n")
            f.write("\n")

            all_var_states = {}
            all_flow_paths = []
            for s in states:
                s_meta = meta.get(s, {})
                v_states = s_meta.get("variable_states", {})
                for var_name, var_info in v_states.items():
                    if not isinstance(var_info, dict): continue
                    if var_name not in all_var_states:
                        all_var_states[var_name] = {
                            "state": var_info.get("state", "SAFE"),
                            "type": var_info.get("type") or "—",
                            "constraints": list(var_info.get("constraints") or [])
                        }
                    else:
                        existing = all_var_states[var_name]
                        s1, s2 = existing["state"], var_info.get("state", "SAFE")
                        merged_s = "SAFE"
                        if "TAINTED" in (s1, s2): merged_s = "TAINTED"
                        elif "UNSAFE" in (s1, s2): merged_s = "UNSAFE"
                        elif "CONSTANT" in (s1, s2): merged_s = "CONSTANT"
                        merged_c = list(set((existing.get("constraints") or []) + (var_info.get("constraints") or [])))
                        all_var_states[var_name] = {
                            "state": merged_s,
                            "type": var_info.get("type") or existing.get("type") or "—",
                            "constraints": merged_c
                        }
                for path in s_meta.get("flow_paths", []):
                    if isinstance(path, dict) and path not in all_flow_paths: all_flow_paths.append(path)
            
            if all_var_states:
                f.write("## Dynamic Variable Tracking\n\n")
                f.write("| Variable | State | Type | Constraints |\n")
                f.write("| :--- | :--- | :--- | :--- |\n")
                for var_name in sorted(all_var_states.keys()):
                    info = all_var_states[var_name]
                    constraints_str = ", ".join([self._sanitize_for_table(x) for x in info["constraints"]]) if info["constraints"] else "—"
                    f.write(f"| `{var_name}` | `{info['state']}` | {info['type']} | {constraints_str} |\n")
                f.write("\n")
                
            if all_flow_paths:
                f.write("## Behavior Dataflow Tracking\n\n")
                f.write("```mermaid\ngraph LR\n")
                node_ids = {}
                def get_node_id(name_str):
                    if name_str not in node_ids: node_ids[name_str] = f"node_{len(node_ids)}"
                    return node_ids[name_str]
                connections = set()
                for path in all_flow_paths:
                    src, sink, var = path.get("source", "unknown"), path.get("sink", "unknown"), path.get("variable", "")
                    src_id, sink_id = get_node_id(src), get_node_id(sink)
                    # Aggressive sanitization for mermaid labels
                    safe_src = self._sanitize_for_table(src)
                    safe_sink = self._sanitize_for_table(sink)
                    safe_var = self._sanitize_for_table(var)
                    if var: conn_str = f'    {src_id}["{safe_src}"] -- "{safe_var}" --> {sink_id}["{safe_sink}"]\n'
                    else: conn_str = f'    {src_id}["{safe_src}"] --> {sink_id}["{safe_sink}"]\n'
                    if conn_str not in connections:
                        connections.add(conn_str)
                        f.write(conn_str)
                f.write("```\n\n")

    def export_narrative(self, archetype: str, symbols: List[dict]):
        safe_arch = self._get_safe_filename(archetype)
        filepath = self._safe_path("narratives", f"archetype_{safe_arch}.md")
        total_mass = sum(s.get("mass", 1.0) for s in symbols)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Subsystem Narrative: {archetype}\n\n")
            f.write(f"This subsystem contains {len(symbols)} symbols with a collective mass of {total_mass:.2f}.\n\n")
            f.write(f"## Key Symbols\n")
            key_symbols = sorted(symbols, key=lambda x: x.get("mass", 0), reverse=True)[:10]
            for s in key_symbols: f.write(f"- `[[{s['name']}]]` (Mass: {s.get('mass', 0):.2f}, PE: {s.get('potential_energy', 0):.2f})\n")
            f.write(f"\n## Security Posture\n")
            tainted_count = sum(1 for s in symbols if any(isinstance(data, dict) and data.get("state") == "TAINTED" for data in s.get("variable_states", {}).values()))
            f.write(f"- **Tainted Symbols**: {tainted_count}\n")
            f.write(f"\n## Primary Dataflows\n")
            f.write("| Source | Target | State |\n")
            f.write("|:---|:---|:---|\n")
            count = 0
            for s in symbols:
                for path in s.get("flow_paths", []):
                    f.write(f"| {path.get('source')} | {path.get('sink')} | {path.get('state')} |\n")
                    count += 1
                    if count > 20: break
                if count > 20: break

    def export_warnings(self, warnings: List[dict]):
        filepath = self._safe_path("rules", "warnings.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Docstring & Quality Invariants Warnings\n\n")
            f.write("| Symbol | File | Warnings |\n")
            f.write("|:---|:---|:---|\n")
            for w in warnings: f.write(f"| [[{self._get_safe_filename(w['name'])}|{w['name'].split(':')[-1]}]] | {w['file']} | {', '.join(w['warnings'])} |\n")

    def export_vulnerabilities(self, vulns: List[dict]):
        """
        Generate a structured, CWE-grouped vulnerabilities.md in the vault.
        Includes executive summary, per-CWE findings, taint flow context,
        and a CWE Top 40 coverage matrix.
        """
        filepath = self._safe_path("rules", "vulnerabilities.md")

        # CWE reference catalogue (subset of Top 40 relevant to dynamic analysis)
        CWE_CATALOGUE = {
            "CWE-79":   ("Cross-site Scripting (XSS)",                "APP Data",    "Tainted user input rendered in HTML output without escaping."),
            "CWE-89":   ("SQL Injection",                              "DataBase",    "Tainted input concatenated into a SQL query."),
            "CWE-22":   ("Path Traversal",                             "System Call", "User-controlled input used to construct file paths."),
            "CWE-78":   ("OS Command Injection",                       "System Call", "Tainted input passed to exec/system/shell_exec."),
            "CWE-94":   ("Code Injection",                             "System Call", "Tainted input passed to eval/exec/create_function."),
            "CWE-77":   ("Command Injection",                          "System Call", "User-controlled input injected into shell commands."),
            "CWE-98":   ("Remote File Inclusion",                      "System Call", "Tainted include/require path from user input."),
            "CWE-502":  ("Deserialization of Untrusted Data",          "System Call", "Unsafe deserialization (pickle/yaml.load without SafeLoader)."),
            "CWE-200":  ("Exposure of Sensitive Information",          "Data Flow",   "Sensitive data exposed via response, log, or error output."),
            "CWE-532":  ("Insertion of Sensitive Information into Log", "Data Flow",   "Sensitive fields (password/token) written to log sinks."),
            "CWE-862":  ("Missing Authorization",                      "Object Access","Public API/entrypoint with no detected authorization checks."),
            "CWE-863":  ("Incorrect Authorization",                    "Object Access","Authorization rule present but implementation lacks checks."),
            "CWE-918":  ("Server-Side Request Forgery (SSRF)",         "System Call", "Tainted URL passed to file_get_contents or HTTP client."),
            "CWE-798":  ("Use of Hard-coded Credentials",              "Data",        "Credentials or API keys present as string literals in code."),
            "CWE-400":  ("Uncontrolled Resource Consumption",          "DOS",         "Infinite loops, missing timeouts, or unbounded collection growth."),
            "CWE-312":  ("Cleartext Storage of Sensitive Information",  "Data Flow",   "Sensitive data written to storage without encryption."),
            "CWE-601":  ("Open Redirect",                              "System Call", "Tainted value used in HTTP Location header without validation."),
            "CWE-276":  ("Incorrect Default Permissions",              "Object Access","File permissions set to world-writable (chmod 777)."),
            "CWE-362":  ("Race Condition",                             "System Call", "Concurrent access to shared state without synchronization."),
            "CWE-1188": ("Insecure Default Variable Initialization",   "Code Quality","DEBUG=True or other insecure defaults in production code."),
            "CWE-614":  ("Sensitive Cookie Without Secure Attribute",  "Data Flow",   "Cookie set with tainted value without Secure/HttpOnly flags."),
        }

        SEVERITY_ICON = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}

        # Group findings by CWE
        by_cwe: Dict[str, List[dict]] = {}
        for v in vulns:
            cwe = v.get("cwe", "CWE-Unknown")
            by_cwe.setdefault(cwe, []).append(v)

        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for v in vulns:
            sev = v.get("severity", "LOW").upper()
            if sev in severity_counts:
                severity_counts[sev] += 1

        detected_cwes = set(by_cwe.keys())

        with open(filepath, "w", encoding="utf-8") as f:
            # ── Header ────────────────────────────────────────────────────────
            f.write("---\ntype: security-report\ntags: [security, cwe, vulnerabilities]\n---\n\n")
            f.write("# 🛡️ Security Vulnerability Report\n\n")
            f.write("> Auto-generated by Quantum Brain SLM via `qbrain library`.\n")
            f.write("> All findings are heuristic — verify each one manually before acting.\n\n")

            # ── Executive Summary ─────────────────────────────────────────────
            f.write("## Executive Summary\n\n")
            total = len(vulns)
            f.write(f"**Total Findings:** {total}\n\n")
            f.write("| Severity | Count |\n|:---|---:|\n")
            for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                icon = SEVERITY_ICON.get(sev, "")
                f.write(f"| {icon} {sev} | {severity_counts[sev]} |\n")
            f.write("\n")

            if not vulns:
                f.write("> ✅ No vulnerabilities detected in this scan.\n\n")
            else:
                f.write("### Top Findings\n\n")
                critical_high = [v for v in vulns if v.get("severity", "").upper() in ("CRITICAL", "HIGH")]
                for v in critical_high[:5]:
                    icon = SEVERITY_ICON.get(v.get("severity","LOW").upper(),"")
                    cwe = v.get("cwe", "CWE-?")
                    fname = (v.get("function") or v.get("name") or "unknown").split(":")[-1]
                    f.write(f"- {icon} **[{cwe}]** `{fname}` — {(v.get('description') or '')[:120]}\n")
                f.write("\n")

            # ── Per-CWE Sections ──────────────────────────────────────────────
            f.write("---\n\n## Findings by CWE\n\n")
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            sorted_cwes = sorted(by_cwe.keys(), key=lambda c: min(
                severity_order.get(v.get("severity","LOW").upper(), 4) for v in by_cwe[c]
            ))

            for cwe in sorted_cwes:
                findings = by_cwe[cwe]
                cat_info = CWE_CATALOGUE.get(cwe)
                cwe_title = cat_info[0] if cat_info else "Unknown Weakness"
                cwe_desc  = cat_info[2] if cat_info else ""
                cwe_num = cwe.replace("CWE-", "")

                f.write(f"### {cwe}: {cwe_title}\n\n")
                if cwe_desc:
                    f.write(f"> {cwe_desc}  \n")
                f.write(f"> Reference: [MITRE {cwe}](https://cwe.mitre.org/data/definitions/{cwe_num}.html)\n\n")
                f.write("| Severity | Symbol | File | Finding |\n")
                f.write("|:---|:---|:---|:---|\n")
                for v in sorted(findings, key=lambda x: severity_order.get(x.get("severity","LOW").upper(), 4)):
                    sev = v.get("severity", "LOW").upper()
                    icon = SEVERITY_ICON.get(sev, "")
                    name = v.get("function") or v.get("name") or "unknown"
                    safe_link = v.get("safe_link") or self._get_safe_filename(name)
                    display_name = name.split(":")[-1]
                    file_path = v.get("file", "unknown")
                    desc = (v.get("description") or v.get("message") or "").replace("|", "\\|")
                    f.write(f"| {icon} {sev} | [[{safe_link}\\|{display_name}]] | {file_path} | {desc} |\n")
                f.write("\n")

            # ── CWE Top 40 Coverage Matrix ────────────────────────────────────
            f.write("---\n\n## CWE Top 40 Detection Coverage\n\n")
            f.write("Shows which CWE Top 40 classes this pipeline can detect vs. where it has gaps.\n\n")
            f.write("| Rank | CWE | Description | Detected | Method |\n")
            f.write("|:---:|:---|:---|:---:|:---|\n")

            COVERAGE_MAP = [
                (1,  "CWE-79",  "XSS",                    True,  "Taint→echo/innerHTML sink (`scan_taint_to_sink`)"),
                (2,  "CWE-787", "Out-of-bounds Write",    False, "Memory — requires ASan/runtime instrumentation"),
                (3,  "CWE-89",  "SQL Injection",           True,  "Taint→query sink + language_parser regex"),
                (4,  "CWE-352", "CSRF",                    False, "Needs framework-level token inspection"),
                (5,  "CWE-22",  "Path Traversal",          True,  "Taint→fopen/open sink (`scan_taint_to_sink`)"),
                (6,  "CWE-125", "Out-of-bounds Read",     False, "Memory — requires ASan"),
                (7,  "CWE-78",  "OS Command Injection",   True,  "Taint→exec/system/subprocess sink"),
                (8,  "CWE-416", "Use After Free",          False, "Memory — requires ASan"),
                (9,  "CWE-862", "Missing Authorization",  True,  "Business rule + entrypoint heuristic"),
                (10, "CWE-434", "Unrestricted Upload",    False, "Needs HTTP multipart/form-data analysis"),
                (11, "CWE-94",  "Code Injection",          True,  "Taint→eval/exec sink + language_parser"),
                (12, "CWE-20",  "Improper Input Validation",False,"Needs per-field schema validation analysis"),
                (13, "CWE-77",  "Command Injection",      True,  "Taint→popen/passthru sink"),
                (14, "CWE-287", "Improper Authentication",False, "Needs session/auth framework analysis"),
                (15, "CWE-269", "Improper Privilege Mgmt",False, "Business logic — needs policy rules"),
                (16, "CWE-502", "Deserialization",         True,  "language_parser regex → `scan_from_parser_warnings`"),
                (17, "CWE-200", "Sensitive Info Exposure", True,  "Log-sink + name heuristic (`scan_sensitive_exposure`)"),
                (18, "CWE-863", "Incorrect Authorization", True,  "Business rule cross-reference"),
                (19, "CWE-918", "SSRF",                    True,  "Taint→file_get_contents sink"),
                (20, "CWE-119", "Buffer Ops",              False, "Memory — requires ASan"),
                (21, "CWE-476", "NULL Dereference",        False, "Memory — requires ASan"),
                (22, "CWE-798", "Hardcoded Credentials",  True,  "Regex + language_parser → `scan_hardcoded_credentials`"),
                (23, "CWE-190", "Integer Overflow",        False, "Memory — requires UBSan"),
                (24, "CWE-400", "Resource Consumption",   True,  "`scan_resource_consumption` (loops, no timeout)"),
                (25, "CWE-306", "Missing Auth for Fn",    True,  "Covered by CWE-862 scanner"),
                (26, "CWE-770", "Allocation w/o Limit",   False, "Needs memory profiling / fuzzing"),
                (27, "CWE-668", "Exposure to Wrong Sphere",False, "Needs access-control domain model"),
                (28, "CWE-74",  "Special Element Injection",True, "Partially — via taint→sink coverage"),
                (29, "CWE-427", "Uncontrolled Search Path",False,"Needs PATH env analysis"),
                (30, "CWE-639", "Authorization Bypass",   True,  "Partially via CWE-863 scanner"),
                (31, "CWE-532", "Sensitive Info in Logs", True,  "`scan_sensitive_exposure` + taint→log sink"),
                (32, "CWE-732", "Incorrect Permissions",  True,  "language_parser chmod 777 check"),
                (33, "CWE-601", "Open Redirect",           True,  "Taint→header sink"),
                (34, "CWE-362", "Race Condition",          True,  "language_parser global keyword check"),
                (35, "CWE-522", "Weak Credentials",        False, "Needs hash strength analysis (bcrypt cost etc.)"),
                (36, "CWE-276", "Incorrect Default Perms", True,  "language_parser chmod check"),
                (37, "CWE-203", "Observable Discrepancy", False, "Needs timing analysis"),
                (38, "CWE-59",  "Link Following",          False, "Needs filesystem symlink analysis"),
                (39, "CWE-843", "Type Confusion",          False, "Memory — requires type-san"),
                (40, "CWE-312", "Cleartext Storage",       True,  "`scan_cleartext_storage` (sensitive + write sink)"),
            ]

            detected_count = sum(1 for _, _, _, d, _ in COVERAGE_MAP if d)
            for rank, cwe_id, desc, detected, method in COVERAGE_MAP:
                status = "✅" if detected else "❌"
                highlight = cwe_id if cwe_id in detected_cwes else cwe_id
                f.write(f"| {rank} | **{highlight}** | {desc} | {status} | {method} |\n")

            f.write(f"\n**Coverage: {detected_count}/40 CWE Top 40 classes detectable** ")
            f.write(f"({detected_count * 100 // 40}% detection rate)\n\n")
            f.write("> ⚠️ Classes marked ❌ require memory instrumentation (ASan/UBSan), ")
            f.write("runtime fuzzing, or framework-level analysis beyond static regex/taint tracing.\n")


    def export_hotspots(self, hotspots: dict):
        filepath = self._safe_path("rules", "hotspots.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 📊 Codebase Cognitive & Complexity Hotspots\n\n")
            f.write("## 🏋️ Complexity Hotspots (Highest Mass)\n")
            f.write("| Symbol | File | Mass | Archetype |\n")
            f.write("|:---|:---|:---|:---|\n")
            for h in hotspots.get("complexity", []): f.write(f"| [[{self._get_safe_filename(h['name'])}|{h['name'].split(':')[-1]}]] | {h.get('file', 'unknown')} | {h['mass']:.1f} | {h.get('archetype', '—')} |\n")
            f.write("\n## ⚡ Attention Hotspots (Highest Drift / Attention Debt)\n")
            f.write("| Symbol | File | Potential Energy | Archetype |\n")
            f.write("|:---|:---|:---|:---|\n")
            for h in hotspots.get("attention", []): f.write(f"| [[{self._get_safe_filename(h['name'])}|{h['name'].split(':')[-1]}]] | {h.get('file', 'unknown')} | {h['potential_energy']:.2f} | {h.get('archetype', '—')} |\n")

    def export_archetypes(self, groups: dict):
        filepath = self._safe_path("rules", "archetypes.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🧩 Codebase Semantic Archetypes\n\n")
            for arch, symbols in groups.items():
                title_arch = "-".join([w.capitalize() for w in arch.split("-")])
                safe_arch = self._get_safe_filename(arch)
                f.write(f"## {title_arch} (Narrative: [[archetype_{safe_arch}]])\n")
                for s in symbols[:15]:
                    conf_str = f" (Confidence: {s['confidence']:.2%})" if "confidence" in s else ""
                    f.write(f"- [[{self._get_safe_filename(s['name'])}|{s['name'].split(':')[-1]}]] {conf_str}\n")
                f.write("\n")

    def export_branch_diff(self, diff: dict):
        filepath = self._safe_path("changes", "branch_diff.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🌿 Branch Diff & Semantic Distance Report\n\n")
            f.write(f"**Comparing current workspace against:** `{diff.get('target_branch', 'main')}`\n\n")
            f.write(f"**Semantic Distance:** `{diff.get('semantic_distance', 0.0)}`\n\n")
            f.write("## 📝 Modified Files & Relevance Scores\n")
            f.write("| File | Status | Churn | Relevance |\n")
            f.write("|:---|:---|:---|:---|\n")
            for fl in diff.get("files", []): f.write(f"| {fl['file']} | {fl.get('status')} | {fl.get('churn')} | {fl.get('relevance_score')} |\n")
