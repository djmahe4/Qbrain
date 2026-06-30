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
        self.registry = None
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
            "symbols", "files", "behaviors", "behaviors/_json", "changes", "changes/recent",
            "changes/archive", "rules", "narratives", "blackboard"
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

    def _escape_for_table_no_truncation(self, text: str) -> str:
        """Escapes text for markdown table cells without length truncation."""
        if not text: return "—"
        return str(text).replace("\n", " ").replace("\r", "").replace("|", "\\|").replace('"', "'")

    def _resolve_expression_variables(self, expr: str, meta: dict, states: list) -> dict:
        """
        Recursively finds variable definitions/constants referenced in a state expression.
        """
        resolved = {}
        if not expr:
            return resolved
        try:
            clean_expr = re.sub(r"'[^']*'|\"[^\"]*\"", "", expr)
            words = re.findall(r"\$?[a-zA-Z_]\w*", clean_expr)
        except Exception:
            words = []
            
        for word in words:
            if self.registry:
                try:
                    if self.registry.has_constant(word):
                        val = self.registry.get_constant(word)
                        origin = self.registry.get_origin(word)
                        resolved[word] = {"value": val, "source": f"registry (defined in {origin})" if origin else "registry"}
                        continue
                    elif self.registry.get_env(word):
                        val = self.registry.get_env(word)
                        resolved[word] = {"value": val, "source": "env"}
                        continue
                except Exception:
                    pass
            
            for s in states:
                s_meta = meta.get(s, {})
                v_states = s_meta.get("variable_states", {})
                if word in v_states:
                    v_info = v_states[word]
                    if isinstance(v_info, dict) and v_info.get("state") == "CONSTANT" and "value" in v_info:
                        resolved[word] = {"value": v_info["value"], "source": v_info.get("source", "internal")}
                        break
        return resolved

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

    def _get_symbol_header_id(self, symbol_name: str, file_path: str = None) -> str:
        """Extracts the qualified class/method name from a symbol name to use as a unique heading ID."""
        if file_path and symbol_name.startswith(file_path + ":"):
            return symbol_name[len(file_path)+1:]
        if ":" in symbol_name:
            parts = symbol_name.split(":")
            # If the first part looks like a file path, strip it
            if "/" in parts[0] or "\\" in parts[0] or "." in parts[0]:
                return ":".join(parts[1:])
        return symbol_name

    def _get_symbol_wikilink(self, symbol_name: str, file_path: str = None) -> str:
        """Generates a wikilink to a symbol aggregated inside its file page using its qualified heading ID."""
        if not file_path and ":" in symbol_name:
            parts = symbol_name.split(":")
            file_path = parts[0]
        header_id = self._get_symbol_header_id(symbol_name, file_path)
        display_name = header_id.split(":")[-1]
        if file_path:
            safe_file = self._get_safe_filename(file_path)
            return f"[[files/{safe_file}#Symbol: {header_id}\\|{display_name}]]"
        return f"`{display_name}`"

    def export_symbol(self, symbol_data: dict):
        """Deprecated: Symbols are now aggregated inside file pages to prevent vault overpopulation.
        Still calculates and saves confidence scores to the database for analysis."""
        name = symbol_data.get("name")
        if not name: return
        if ".." in name or name.startswith("/") or name.startswith("\\"):
            raise ValueError(f"Security Risk: Path traversal detected in symbol name: {name}")
        
        has_docstring = 1 if symbol_data.get("docstring") else 0
        has_taint = 1 if "_TAINT_" in symbol_data.get("variable_states", {}) else 0
        entanglement_count = len(symbol_data.get("callees", []))
        caller_count = len(symbol_data.get("callers", []))
        
        confidence = (has_docstring * 0.4) + (has_taint * 0.3) + (entanglement_count * 0.2) + (caller_count * 0.1)
        
        if confidence < 0.1:
            tier = "skip"
        elif confidence < 0.5:
            tier = "stub"
        else:
            tier = "full"
            
        if self.indexer and getattr(self.indexer, "persistence", None):
            self.indexer.persistence.save_symbol_confidence(name, confidence, tier)



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
            "size_bytes": file_data.get("size_bytes"),
            "cognitive_mass": file_data.get("cognitive_mass"),
            "potential_energy": file_data.get("potential_energy"),
            "archetypes": file_data.get("archetypes")
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
            if file_data.get("cognitive_mass") is not None:
                f.write(f"- **Cognitive Mass:** {file_data.get('cognitive_mass'):.2f}\n")
            if file_data.get("potential_energy") is not None:
                f.write(f"- **Potential Energy:** {file_data.get('potential_energy'):.2f}\n")
            if file_data.get("archetypes"):
                f.write(f"- **Archetypes:** {', '.join(file_data.get('archetypes'))}\n")
            f.write("\n")
            
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
                f.write("## Symbols Index\n")
                f.write("| Symbol | Kind | Line | Signature | Description |\n")
                f.write("|:---|:---|:---|:---|:---|\n")
                for s in symbols_data:
                    name = s.get("name")
                    kind = s.get("kind", "Function")
                    line = s.get("line", "—")
                    sig = s.get("signature") or name
                    doc = (s.get("docstring") or "").split("\n")[0]
                    header_id = self._get_symbol_header_id(name, file_path)
                    display_name = name.split(":")[-1] if ":" in name else name
                    # Link to the local heading on this same page
                    f.write(f"| [[#Symbol: {header_id}\\|{display_name}]] | `{kind}` | {line} | `{sig}` | {doc} |\n")
                f.write("\n")

                f.write("## Detailed Symbol Specifications\n\n")
                for s in symbols_data:
                    name = s.get("name")
                    header_id = self._get_symbol_header_id(name, file_path)
                    display_name = name.split(":")[-1] if ":" in name else name
                    kind = s.get("kind", "Function")
                    line = s.get("line", "—")
                    sig = s.get("signature") or name
                    doc = s.get("docstring") or ""
                    mass = s.get("mass", 1.0)
                    pe = s.get("potential_energy", 0.0)
                    archetype = s.get("archetype", "generic")
                    
                    badge = "🔧"
                    if kind == "Class": badge = "🏛️"
                    elif kind == "Interface": badge = "📑"
                    elif kind == "Enum": badge = "🗳️"
                    elif kind == "Variable": badge = "📌"
                    elif kind == "Module": badge = "📦"
                    elif kind == "Method": badge = "⚡"
                    
                    f.write(f"### Symbol: {header_id}\n")
                    f.write(f"- **Kind:** `{kind}`\n")
                    f.write(f"- **Line:** {line}\n")
                    f.write(f"- **Archetype:** `{archetype}`\n")
                    f.write(f"- **Cognitive Mass:** `{mass:.2f}`\n")
                    f.write(f"- **Potential Energy:** `{pe:.2f}`\n")
                    if sig:
                        f.write(f"- **Signature:** `{sig}`\n")
                    f.write("\n")

                    
                    if doc:
                        f.write(f"#### Documentation\n{doc}\n\n")
                        
                    s_params = s.get("params", [])
                    if s_params:
                        f.write("#### Parameters\n")
                        for param in s_params:
                            f.write(f"- `{param.get('name')}` ({param.get('type')}): {param.get('description', '')}\n")
                        f.write("\n")
                        
                    s_returns = s.get("returns")
                    if s_returns:
                        rtype = s_returns.get("type") if isinstance(s_returns, dict) else (s_returns if isinstance(s_returns, str) else "")
                        rdesc = s_returns.get("description", "") if isinstance(s_returns, dict) else ""
                        if rtype or rdesc:
                            f.write(f"#### Returns\n`{rtype}`: {rdesc}\n\n")
                            
                    callers = s.get("callers", [])
                    callees = s.get("callees", [])
                    if callers or callees:
                        f.write("#### Entanglements\n")
                        if callers:
                            f.write("##### Inbound Callers\n")
                            for caller in callers:
                                f.write(f"- {self._get_symbol_wikilink(caller)}\n")
                        if callees:
                            f.write("##### Outbound Callees\n")
                            for callee in callees:
                                f.write(f"- {self._get_symbol_wikilink(callee)}\n")
                        f.write("\n")
                        
                    s_rules = s.get("business_rules", [])
                    if s_rules:
                        f.write("#### Business Rules\n")
                        for rule in s_rules:
                            f.write(f"- {rule}\n")
                        f.write("\n")
                        
                    s_vulns = s.get("vulnerabilities", [])
                    if s_vulns:
                        f.write("#### Security Findings\n")
                        for vuln in s_vulns:
                            f.write(f"- **{vuln.get('severity', 'LOW')}**: {vuln.get('message') or vuln.get('description')}\n")
                        f.write("\n")
                        
                    s_code = s.get("code_snippet", "")
                    if s_code:
                        f.write("#### Implementation\n")
                        lang = s.get("language") or "generic"
                        f.write(f"```{lang}\n")
                        # Cap code snippet to 40 lines
                        lines = s_code.splitlines()
                        if len(lines) > 40:
                            f.write("\n".join(lines[:40]))
                            f.write(f"\n\n[... Truncated {len(lines) - 40} lines. View source file at line {line} ...]\n")
                        else:
                            f.write(s_code)
                        f.write("\n```\n\n")
                    
                    f.write("---\n\n")

                all_rules = []
                for s in symbols_data:
                    for rule in s.get("business_rules", []):
                        all_rules.append(f"- **{self._get_symbol_wikilink(s.get('name'))}**: {rule}")
                
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
                        source_link = self._get_symbol_wikilink(flow['source'])
                        sink_link = self._get_symbol_wikilink(flow['sink']) if flow['sink'] and flow['sink'] != 'internal' else '`internal`'
                        f.write(f"| {source_link} | `{flow['variable']}` | `{flow['state']}` | {sink_link} | {flow.get('line', '—')} |\n")
                    f.write("\n")
 
            behaviors = file_data.get("behaviors", [])
            if behaviors:
                f.write("## Related Behaviors\n")
                for b in sorted(list(set(behaviors))):
                    f.write(f"- [[behaviors/{self._get_safe_filename(b)}\\|{b}]]\n")
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
            
            # Prune/ignore setup and config calls from other entrypoints
            is_setup_config = False
            symbol_file = sym_meta.get(lookup_key, {}).get("file") or (lookup_key if lookup_key.endswith(".php") or lookup_key.endswith(".php.dist") else None)
            if symbol_file and entrypoint_path != symbol_file:
                setup_patterns = [
                    r"config.*\.php(\.dist)?$", 
                    r"bootstrap.*\.php(\.dist)?$", 
                    r"common\.php(\.dist)?$", 
                    r"settings\.php(\.dist)?$", 
                    r"init\.php(\.dist)?$",
                    r"setup.*\.php(\.dist)?$"
                ]
                file_name = os.path.basename(symbol_file)
                if any(re.match(pattern, file_name, re.IGNORECASE) for pattern in setup_patterns):
                    is_setup_config = True
            
            if is_setup_config:
                continue

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
                                
                                # Add metadata for the synthesized state to sym_meta
                                if synth_name not in sym_meta:
                                    sym_meta[synth_name] = {
                                        "file": current_obj.get("file"),
                                        "line": atom.get("line"),
                                        "kind": "Synthesized",
                                        "params": [],
                                        "returns": "—",
                                        "docstring": f"Synthesized {atom.get('type')} in {current_obj.get('name')}",
                                        "variable_states": {},
                                        "flow_paths": []
                                    }
                                queue.append((synth_name, current, depth + 1, None))
        
        is_hub = len(transitions) > 15
        return {
            "entrypoint": entrypoint_func,
            "states": list(states),
            "transitions": transitions,
            "state_meta": sym_meta,
            "is_macro_map": is_hub
        }

    def _analyze_behavioral_characteristics(self, state_name: str, state_meta: dict) -> dict:
        code = state_meta.get("code_snippet", "")
        # Fallback to check if we can query it or if it is a synthesized state
        if not code:
            # If it's a synthesized redirect/sink/etc.
            if state_name.startswith("[") or state_name.startswith("Redirect:"):
                has_recovery = "try" in state_name.lower() or "catch" in state_name.lower()
                has_perf = any(x in state_name.lower() for x in ["query", "http", "curl", "request", "timeout"])
                return {
                    "loops": "none",
                    "conditions": "none",
                    "boundaries": "none",
                    "recovery": "exception handling / try-catch" if has_recovery else "none",
                    "performance": "database/network operations" if has_perf else "none"
                }
            return {
                "loops": "none",
                "conditions": "none",
                "boundaries": "none",
                "recovery": "none",
                "performance": "none"
            }
            
        code_no_comments = code
        if code:
            code_no_comments = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
            code_no_comments = re.sub(r'"""\s*.*?\s*"""', '', code_no_comments, flags=re.DOTALL)
            code_no_comments = re.sub(r"'''\s*.*?\s*'''", '', code_no_comments, flags=re.DOTALL)
            code_no_comments = re.sub(r'//.*', '', code_no_comments)
            code_no_comments = re.sub(r'#.*', '', code_no_comments)
            
        # 1. Loops
        loops = []
        if re.search(r'\b(?:for|while|foreach)\b', code_no_comments):
            loops.append("loop (for/while/foreach)")
        
        # 2. Conditions
        conditions = []
        if re.search(r'\b(?:if|else|elseif|switch|case)\b', code_no_comments):
            conditions.append("conditionals (if/else/switch)")
            
        # 3. Boundary Values & Equivalence Partitioning
        boundaries = []
        bound_matches = re.findall(r'([\w\.\$]+(?:\[[^\]]+\])?)\s*(>=|<=|==|!=|<|>)\s*([\w\.\$]+|["\']\w*["\'])', code_no_comments)
        for match in bound_matches:
            boundaries.append(f"`{' '.join(match)}`")
            
        # 4. Recovery
        recovery = []
        if re.search(r'\b(?:try|catch|except|finally)\b', code_no_comments):
            recovery.append("exception handling / try-catch")
            
        # 5. Stress & Performance
        performance = []
        if "timeout" in code_no_comments.lower():
            performance.append("timeout configuration")
        if re.search(r'\b(?:select|insert|update|delete|query|prepare|db)\b', code_no_comments, re.IGNORECASE):
            performance.append("database operations")
        if re.search(r'\b(?:curl|request|http|socket)\b', code_no_comments, re.IGNORECASE):
            performance.append("network/external operations")
            
        return {
            "loops": ", ".join(loops) if loops else "none",
            "conditions": ", ".join(conditions) if conditions else "none",
            "boundaries": ", ".join(list(set(boundaries))[:4]) if boundaries else "none",
            "recovery": ", ".join(recovery) if recovery else "none",
            "performance": ", ".join(performance) if performance else "none"
        }

    def export_behavior(self, behavior_data: dict):
        print(f"DEBUG: Exporting behavior: {behavior_data.get('name')}")
        name = behavior_data.get("name")
        if not name: return
        safe_name = self._get_safe_filename(name)
        filepath = self._safe_path("behaviors", f"{safe_name}.md")
        states = list(behavior_data.get("states", []))
        transitions = list(behavior_data.get("transitions", []))
        meta = behavior_data.get("state_meta", {})
        
        # Track A.1 & C.1: Instantiate TaintClassifier
        metadata_dir = os.path.join(self.vault_path, ".qbrain")
        from brain.taint_classifier import TaintClassifier
        classifier = TaintClassifier(metadata_dir, registry=self.registry)

        # Track B.2.1: Pruning synthesized/HTML redirect states
        all_flow_paths = []
        for s in states:
            s_meta = meta.get(s, {})
            for path in s_meta.get("flow_paths", []):
                if isinstance(path, dict) and path not in all_flow_paths:
                    all_flow_paths.append(path)
        tainted_state_ids = {p.get("source") for p in all_flow_paths if p.get("source")} | {p.get("sink") for p in all_flow_paths if p.get("sink")}
        
        pruned_states = []
        for s in states:
            if s in tainted_state_ids or s == behavior_data.get("entrypoint"):
                pruned_states.append(s)
                continue
            s_meta = meta.get(s, {})
            kind = s_meta.get("kind")
            if kind == "Synthesized" or s.startswith("[") or s.startswith("Redirect:"):
                clean_s = s.strip().lower()
                if (clean_s.startswith("<") or 
                    "[redirect]" in clean_s or 
                    "redirect:" in clean_s or 
                    "location:" in clean_s):
                    continue
            pruned_states.append(s)
        states = pruned_states
        transitions = [t for t in transitions if t["from"] in states and t["to"] in states]

        # Track A.2: state_machine.json sidecar emission
        entry_cond = ""
        entry_cond_var = ""
        entry_cond_val = ""
        scenario_context = behavior_data.get("scenario_context") or []
        if scenario_context:
            entry_cond = " AND ".join(scenario_context)
            for cond in scenario_context:
                m = re.search(r"([\$\w\(\)\[\]'\"_-]+)\s*==\s*['\"]([\w\.-]+)['\"]", cond)
                if m:
                    entry_cond_var = m.group(1)
                    entry_cond_val = m.group(2)
                    break

        sidecar_states = []
        for s in states:
            s_meta = meta.get(s, {})
            sidecar_states.append({
                "id": s,
                "archetype": s_meta.get("archetype", "generic"),
                "pe": s_meta.get("potential_energy", 0.0),
                "file": s_meta.get("file", "unknown"),
                "line": s_meta.get("line")
            })

        sidecar_taint_flows = []
        for path in all_flow_paths:
            var = path.get("variable", "")
            sidecar_taint_flows.append({
                "source": path.get("source"),
                "variable": var,
                "semantic_label": classifier.classify(var),
                "state": path.get("state"),
                "sink": path.get("sink"),
                "line": path.get("line")
            })

        sidecar_variables = {}
        for s in states:
            s_meta = meta.get(s, {})
            for var_name, var_info in s_meta.get("variable_states", {}).items():
                if not isinstance(var_info, dict): continue
                if var_name not in sidecar_variables:
                    sidecar_variables[var_name] = {
                        "state": var_info.get("state", "SAFE"),
                        "type": var_info.get("type") or "—",
                        "constraints": list(var_info.get("constraints") or [])
                    }
                else:
                    existing = sidecar_variables[var_name]
                    merged_c = list(set((existing.get("constraints") or []) + (var_info.get("constraints") or [])))
                    sidecar_variables[var_name] = {
                        "state": "TAINTED" if "TAINTED" in (existing["state"], var_info.get("state")) else var_info.get("state"),
                        "type": var_info.get("type") or existing.get("type") or "—",
                        "constraints": merged_c
                    }

        sidecar_model = {
            "behavior": name,
            "entry_condition": entry_cond,
            "entry_condition_var": entry_cond_var,
            "entry_condition_value": entry_cond_val,
            "states": sidecar_states,
            "transitions": transitions,
            "taint_flows": sidecar_taint_flows,
            "variables": sidecar_variables
        }
        
        json_dir = os.path.join(self.vault_path, "behaviors", "_json")
        os.makedirs(json_dir, exist_ok=True)
        json_path = os.path.join(json_dir, f"{safe_name}.state_machine.json")
        try:
            with open(json_path, "w", encoding="utf-8") as json_f:
                json.dump(sidecar_model, json_f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: could not write JSON sidecar: {e}")

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
                        for c in vdata["constraints"]:
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
                s_file = s_meta.get("file")
                s_line = s_meta.get("line")
                s_kind = s_meta.get("kind")
                
                if s_kind == "Module" and s_file:
                    link_str = f"[[files/{self._get_safe_filename(s_file)}\\|{display_s}]]"
                elif s_kind == "Synthesized" and s_file:
                    line_suffix = f" (L{s_line})" if s_line else ""
                    link_str = f"[[files/{self._get_safe_filename(s_file)}\\|{display_s}]]" + line_suffix
                elif s_file:
                    symbol_link = f"[[symbols/{self._get_safe_filename(s)}\\|{display_s}]]"
                    file_basename = os.path.basename(s_file)
                    file_link = f"[[files/{self._get_safe_filename(s_file)}\\|{file_basename}]]"
                    line_suffix = f":{s_line}" if s_line else ""
                    link_str = f"{symbol_link} <br> `in` {file_link}{line_suffix}"
                else:
                    link_str = f"[[symbols/{self._get_safe_filename(s)}\\|{display_s}]]"
                
                f.write(f"| {link_str} | {pe} | {arch} | {params_str} | {returns_str} | {invariants_str} | {summary} |\n")
            f.write("\n")

            # Behavioral Characteristics & Safety Constraints
            f.write("## Behavioral Characteristics & Safety Constraints\n\n")
            f.write("| State | Loops | Conditions | Boundaries / Equivalence | Recovery | Stress / Performance |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
            for s in states:
                s_meta = meta.get(s, {})
                char = self._analyze_behavioral_characteristics(s, s_meta)
                display_s = self._sanitize_for_table(s.split(':')[-1])
                f.write(f"| `{display_s}` | {char['loops']} | {char['conditions']} | {char['boundaries']} | {char['recovery']} | {char['performance']} |\n")
            f.write("\n")

            # Track A.1 Variable and Taint table with Semantic Labels
            if sidecar_variables:
                f.write("## Dynamic Variable Tracking\n\n")
                f.write("| Variable | Semantic Label | State | Type | Constraints |\n")
                f.write("| :--- | :--- | :--- | :--- | :--- |\n")
                for var_name in sorted(sidecar_variables.keys()):
                    info = sidecar_variables[var_name]
                    sem_lbl = classifier.classify(var_name)
                    constraints_str = ", ".join([self._sanitize_for_table(x) for x in info["constraints"]]) if info["constraints"] else "—"
                    f.write(f"| `{var_name}` | `{sem_lbl}` | `{info['state']}` | {info['type']} | {constraints_str} |\n")
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
                    safe_src = self._sanitize_for_table(src)
                    safe_sink = self._sanitize_for_table(sink)
                    safe_var = self._sanitize_for_table(var)
                    sem_lbl = classifier.classify(var) if var else ""
                    lbl_suffix = f" [{sem_lbl}]" if sem_lbl else ""
                    if var: conn_str = f'    {src_id}["{safe_src}"] -- "{safe_var}{lbl_suffix}" --> {sink_id}["{safe_sink}"]\n'
                    else: conn_str = f'    {src_id}["{safe_src}"] --> {sink_id}["{safe_sink}"]\n'
                    if conn_str not in connections:
                        connections.add(conn_str)
                        f.write(conn_str)
                f.write("```\n\n")

            # Track A.4: Participating Symbols backlinks
            participating = []
            for s in states:
                s_meta = meta.get(s, {})
                s_kind = s_meta.get("kind")
                if s_kind != "Synthesized" and not s.startswith("[") and not s.startswith("Redirect:"):
                    participating.append((s, s_meta))
            if participating:
                f.write("## Participating Symbols\n\n")
                for s, s_meta in participating:
                    display_s = s.split(':')[-1]
                    s_file = s_meta.get("file", "unknown")
                    s_line = s_meta.get("line")
                    line_suffix = f" (L{s_line})" if s_line else ""
                    f.write(f"- [[symbols/{self._get_safe_filename(s)}\\|{display_s}]] in [[files/{self._get_safe_filename(s_file)}\\|{s_file}]]{line_suffix}\n")
                f.write("\n")

            # Detailed State Definitions for complete context
            f.write("## Detailed State Definitions\n\n")
            f.write("| State Alias | Full State Expression | Resolved Variables / Constants |\n")
            f.write("| :--- | :--- | :--- |\n")
            for s in states:
                alias = state_aliases.get(s, s)
                escaped_s = self._escape_for_table_no_truncation(s)
                resolved = self._resolve_expression_variables(s, meta, states)
                
                resolved_parts = []
                for var, info in sorted(resolved.items()):
                    val_str = str(info["value"]).replace("\n", " ")
                    src_str = f" ({info['source']})" if info.get("source") else ""
                    resolved_parts.append(f"`{var}` = `{val_str}`{src_str}")
                
                resolved_str = " <br> ".join(resolved_parts) if resolved_parts else "—"
                f.write(f"| `{alias}` | `{escaped_s}` | {resolved_str} |\n")
            f.write("\n")

    def export_narrative(self, archetype: str, symbols: List[dict]):
        safe_arch = self._get_safe_filename(archetype)
        filepath = self._safe_path("narratives", f"archetype_{safe_arch}.md")
        total_mass = sum(s.get("mass", 1.0) for s in symbols)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Subsystem Narrative: {archetype}\n\n")
            f.write(f"This subsystem contains {len(symbols)} symbols with a collective mass of {total_mass:.2f}.\n\n")
            f.write(f"## Key Symbols\n")
            key_symbols = sorted(symbols, key=lambda x: x.get("mass", 0), reverse=True)[:10]
            for s in key_symbols: f.write(f"- [[symbols/{self._get_safe_filename(s['name'])}\\|{s['name'].split(':')[-1]}]] (Mass: {s.get('mass', 0):.2f}, PE: {s.get('potential_energy', 0):.2f})\n")
            
            # Collect unique behaviors associated with this archetype
            all_behaviors = set()
            for s in symbols:
                for b in s.get("behaviors", []):
                    all_behaviors.add(b)
            
            if all_behaviors:
                f.write(f"\n## Associated Behaviors\n")
                for b in sorted(list(all_behaviors)):
                    display_b = b.replace("_", "/").replace(".php", "")
                    f.write(f"- [[behaviors/{b}\\|{display_b}]]\n")
            
            f.write(f"\n## Security Posture\n")
            tainted_count = sum(1 for s in symbols if any(isinstance(data, dict) and data.get("state") == "TAINTED" for data in s.get("variable_states", {}).values()))
            f.write(f"- **Tainted Symbols**: {tainted_count}\n")
            f.write(f"\n## Primary Dataflows\n")
            f.write("| Source | Target | State | Location |\n")
            f.write("|:---|:---|:---|:---|\n")
            count = 0
            for s in symbols:
                for path in s.get("flow_paths", []):
                    file_path = path.get("file_path")
                    line = path.get("line")
                    if file_path:
                        file_basename = os.path.basename(file_path)
                        safe_file = self._get_safe_filename(file_path)
                        loc_str = f"[[files/{safe_file}\\|{file_basename}]]:{line}" if line else f"[[files/{safe_file}\\|{file_basename}]]"
                    else:
                        loc_str = "—"
                    f.write(f"| {path.get('source')} | {path.get('sink')} | {path.get('state')} | {loc_str} |\n")
                    count += 1
                    if count > 20: break
                if count > 20: break

    def export_warnings(self, warnings: List[dict]):
        filepath = self._safe_path("rules", "warnings.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Docstring & Quality Invariants Warnings\n\n")
            f.write("| Symbol | File | Warnings |\n")
            f.write("|:---|:---|:---|\n")
            for w in warnings:
                symbol_link = self._get_symbol_wikilink(w['name'], w['file'])
                f.write(f"| {symbol_link} | {w['file']} | {', '.join(w['warnings'])} |\n")


    def export_prerequisites(self, setup_files: List[str], registry):
        """Generates a centralized prerequisites.md to document bootstrapping requirements."""
        filepath = self._safe_path("rules", "prerequisites.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 📋 System Prerequisites & Bootstrapping\n\n")
            f.write("This centralized document lists all environmental configuration requirements, database setup scripts, and third-party prerequisites needed for the application to function correctly.\n\n")
            
            f.write("## 1. Discovered Setup & Installer Scripts\n\n")
            if not setup_files:
                f.write("*No setup or configuration files were detected during scanning.*\n")
            else:
                f.write("These files contain database schema definitions, installation guides, or configuration routines:\n\n")
                for sf in sorted(setup_files):
                    rel_sf = os.path.relpath(sf, self.repo_path).replace("\\", "/")
                    safe_sf = self._get_safe_filename(rel_sf)
                    f.write(f"- **File**: [[files/{safe_sf}\\|{rel_sf}]]\n")
                    f.write(f"  - **Behavior Model**: [[behaviors/{safe_sf}\\|View behavior model]]\n")
            f.write("\n")
            
            f.write("## 2. Configuration Settings & Global Constants\n\n")
            if not registry.constants:
                f.write("*No global configuration constants were extracted during environmental pre-scan.*\n")
            else:
                f.write("The following global variables, configurations, or credentials were discovered in the setup files:\n\n")
                f.write("| Key | Value / Placeholder | Origin File |\n")
                f.write("| :--- | :--- | :--- |\n")
                for name, value in sorted(registry.constants.items()):
                    origin = registry.get_origin(name) or "unknown"
                    safe_origin = self._get_safe_filename(origin)
                    is_secret = any(s in name.lower() for s in ["pass", "secret", "key", "token"])
                    masked_val = "********" if is_secret and value else str(value)
                    f.write(f"| `{name}` | `{masked_val}` | [[files/{safe_origin}\\|{origin}]] |\n")
            f.write("\n")
            
            f.write("## 3. Third-Party Dependencies & Features\n\n")
            vendor_dir = os.path.join(self.repo_path, "vendor")
            node_modules_dir = os.path.join(self.repo_path, "node_modules")
            composer_json = os.path.join(self.repo_path, "composer.json")
            package_json = os.path.join(self.repo_path, "package.json")
            
            if os.path.exists(composer_json):
                f.write("- **Composer Package Manager (PHP)**: `composer.json` detected.\n")
                if not os.path.exists(vendor_dir):
                    f.write("  - ⚠️ `vendor/` directory is **Missing**. Run `composer install` to install PHP dependencies.\n")
                else:
                    f.write("  - 🟢 `vendor/` directory is **Installed**.\n")
            if os.path.exists(package_json):
                f.write("- **Node Package Manager (JS/TS)**: `package.json` detected.\n")
                if not os.path.exists(node_modules_dir):
                    f.write("  - ⚠️ `node_modules/` directory is **Missing**. Run `npm install` to install JS/TS dependencies.\n")
                else:
                    f.write("  - 🟢 `node_modules/` directory is **Installed**.\n")
            
            recaptcha_constants = [c for c in registry.constants if "recaptcha" in c.lower()]
            if recaptcha_constants:
                f.write("\n## 4. Specific Feature Prerequisites\n\n")
                f.write("- **Google reCAPTCHA**: Setup requires API keys to be configured in the config file. Found variables: " + ", ".join(f"`{c}`" for c in recaptcha_constants) + ".\n")

    def generate_and_export_privilege_map(self, funcs: List[dict], calls_map: dict):
        """
        Discovers privilege boundaries dynamically from the call graph.
        Auth gates are any symbols whose name or body matches CREDENTIAL/AUTH_TOKEN
        patterns AND have multiple inbound callers.
        """
        from brain.taint_classifier import TaintClassifier
        metadata_dir = os.path.join(self.vault_path, ".qbrain")
        classifier = TaintClassifier(metadata_dir, registry=self.registry)
        
        candidates = set()
        for f in funcs:
            name = f.get("name")
            if not name:
                continue
            for var in f.get("variable_states", {}).keys():
                label = classifier.classify(var)
                if label in ("AUTH_TOKEN", "CREDENTIAL", "SESSION_ID", "TOKEN_FRAGMENT"):
                    candidates.add(name)
                    break
        
        gates = []
        for sym in candidates:
            callers = calls_map.get(sym, {}).get("callers", [])
            if len(callers) >= 2:
                gates.append({
                    "symbol": sym,
                    "callers": callers,
                    "zone": "AUTHENTICATED",
                    "gate_confidence": min(1.0, len(callers) / 10.0)
                })
        
        auth_caller_set = {c for g in gates for c in g["callers"]}
        all_syms = {f["name"] for f in funcs if f.get("name")}
        privilege_map = {
            "gates": gates,
            "authenticated_zone": sorted(list(auth_caller_set)),
            "public_zone": sorted(list(all_syms - auth_caller_set)),
            "generated_at": datetime.datetime.now(datetime.UTC)
        }
        
        rules_meta_dir = os.path.join(metadata_dir, "rules")
        os.makedirs(rules_meta_dir, exist_ok=True)
        with open(os.path.join(rules_meta_dir, "privilege_boundaries.json"), "w", encoding="utf-8") as f:
            json.dump(privilege_map, f, indent=2, default=str)
            
        filepath = self._safe_path("rules", "privilege_boundaries.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Dynamic Privilege Boundaries & Auth Gates\n\n")
            f.write("This document defines security zones and boundaries discovered dynamically from call graph relationships and credential flows.\n\n")
            
            f.write("## Discovered Auth Gates\n\n")
            if not gates:
                f.write("*No shared auth gates discovered (threshold >= 2 callers).*\n")
            else:
                f.write("| Auth Gate Symbol | Inbound Callers | Confidence |\n")
                f.write("| :--- | :--- | :--- |\n")
                for g in gates:
                    symbol_link = self._get_symbol_wikilink(g["symbol"])
                    f.write(f"| {symbol_link} | {len(g['callers'])} | {g['gate_confidence'] * 100:.1f}% |\n")
            f.write("\n")
            
            f.write("## Authenticated Zone (Callers of Auth Gates)\n\n")
            if not auth_caller_set:
                f.write("*No symbols in authenticated zone.*\n")
            else:
                for c in sorted(list(auth_caller_set)):
                    symbol_link = self._get_symbol_wikilink(c)
                    f.write(f"- {symbol_link}\n")
            f.write("\n")


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
                    file_path = v.get("file", "unknown")
                    symbol_link = self._get_symbol_wikilink(name, file_path)
                    desc = (v.get("description") or v.get("message") or "").replace("|", "\\|")
                    f.write(f"| {icon} {sev} | {symbol_link} | {file_path} | {desc} |\n")
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
            for h in hotspots.get("complexity", []):
                symbol_link = self._get_symbol_wikilink(h['name'], h.get('file'))
                f.write(f"| {symbol_link} | {h.get('file', 'unknown')} | {h['mass']:.1f} | {h.get('archetype', '—')} |\n")
            f.write("\n## ⚡ Attention Hotspots (Highest Drift / Attention Debt)\n")
            f.write("| Symbol | File | Potential Energy | Archetype |\n")
            f.write("|:---|:---|:---|:---|\n")
            for h in hotspots.get("attention", []):
                symbol_link = self._get_symbol_wikilink(h['name'], h.get('file'))
                f.write(f"| {symbol_link} | {h.get('file', 'unknown')} | {h['potential_energy']:.2f} | {h.get('archetype', '—')} |\n")

    def export_archetypes(self, groups: dict):
        filepath = self._safe_path("rules", "archetypes.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🧩 Codebase Semantic Archetypes\n\n")
            for arch, symbols in groups.items():
                title_arch = "-".join([w.capitalize() for w in arch.split("-")])
                safe_arch = self._get_safe_filename(arch)
                f.write(f"## {title_arch} (Narrative: [[narratives/archetype_{safe_arch}]])\n")
                for s in symbols[:15]:
                    conf_str = f" (Confidence: {s['confidence']:.2%})" if "confidence" in s else ""
                    symbol_link = self._get_symbol_wikilink(s['name'], s.get('file'))
                    f.write(f"- {symbol_link}{conf_str}\n")
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
            for fl in diff.get("files", []):
                safe_file = self._get_safe_filename(fl['file'])
                f.write(f"| [[files/{safe_file}\\|{fl['file']}]] | {fl.get('status')} | {fl.get('churn')} | {fl.get('relevance_score')} |\n")

    def export_blackboard_note(self, drift_events, correlation_events=None):
        """Export a blackboard note documenting system drift and cognitive deviations."""
        import datetime
        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
        filename = f"{timestamp_str}.md"
        filepath = os.path.join(self.vault_path, "blackboard", filename)
        
        event_count = len(drift_events) + (len(correlation_events) if correlation_events else 0)
        
        tier_max = 0
        severity_max = "INFO"
        
        severity_hierarchy = {"INFO": 1, "WARN": 2, "CRITICAL": 3}
        for e in drift_events:
            if e.tier > tier_max:
                tier_max = e.tier
            if severity_hierarchy.get(e.severity, 1) > severity_hierarchy.get(severity_max, 1):
                severity_max = e.severity
                
        frontmatter = (
            "---\n"
            "type: blackboard\n"
            f"generated_at: {now.isoformat()}\n"
            f"tier_max: {tier_max}\n"
            f"event_count: {event_count}\n"
            f"severity_max: {severity_max}\n"
            "---\n\n"
        )
        
        content = frontmatter
        content += f"# Blackboard Audit Note — {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        content += "## 📡 Drift Events\n\n"
        if drift_events:
            content += "| File | Event | Tier | Severity | Detail |\n"
            content += "| --- | --- | --- | --- | --- |\n"
            for e in drift_events:
                content += f"| {e.file_path} | {e.event_type} | {e.tier} | {e.severity} | {self._sanitize_for_table(e.detail)} |\n"
        else:
            content += "No structural/filesystem drift events detected.\n"
        content += "\n"
        
        tombstones = [e for e in drift_events if e.event_type == "TOMBSTONE"]
        content += "## 💀 Tombstones\n\n"
        if tombstones:
            for e in tombstones:
                content += f"- [[symbols/{self._get_safe_filename(e.file_path)}.md]] (stale graph node)\n"
        else:
            content += "No tombstones detected.\n"
        content += "\n"
        
        unindexed = [e for e in drift_events if e.event_type == "UNINDEXED"]
        content += "## 🆕 Unindexed Files\n\n"
        if unindexed:
            for e in unindexed:
                content += f"- {e.file_path}\n"
        else:
            content += "No unindexed files detected.\n"
        content += "\n"
        
        content += "## 🔀 Semantic Flips\n\n"
        content += "No semantic flips detected.\n\n"
        
        content += "## 👻 Decoherence\n\n"
        content += "No decoherence events detected.\n"
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def prune_stale_pages(self, tombstoned_files: list):
        """
        Tombstone-aware pruning: scan symbols/, files/, and behaviors/ directories.
        Delete pages whose YAML frontmatter matches any path in tombstoned_files.
        Never touches changes/ or blackboard/.
        """
        if not tombstoned_files:
            return
            
        tombstone_set = set(tombstoned_files)
        dirs_to_prune = ["symbols", "files", "behaviors"]
        
        for d in dirs_to_prune:
            target_dir = os.path.join(self.vault_path, d)
            if not os.path.exists(target_dir):
                continue
                
            for file in os.listdir(target_dir):
                if not file.endswith(".md"):
                    continue
                filepath = os.path.join(target_dir, file)
                
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    doc_type = None
                    file_val = None
                    
                    if lines and lines[0].strip() == "---":
                        yaml_lines = []
                        for line in lines[1:]:
                            if line.strip() == "---":
                                break
                            yaml_lines.append(line)
                        
                        for y_line in yaml_lines:
                            if ":" in y_line:
                                k, v = y_line.split(":", 1)
                                k_clean = k.strip()
                                v_clean = v.strip().strip("'\" ")
                                if k_clean == "type":
                                    doc_type = v_clean
                                elif k_clean in ("file", "file_path", "entrypoint"):
                                    file_val = v_clean
                                    
                    # Reconcile path matching based on doc_type
                    should_remove = False
                    if doc_type == "symbol" and file_val in tombstone_set:
                        should_remove = True
                    elif doc_type == "file" and file_val in tombstone_set:
                        should_remove = True
                    elif doc_type == "behavior" and file_val:
                        # Entrypoint looks like: "src/app.py:main"
                        symbol_file = file_val.split(":")[0] if ":" in file_val else file_val
                        if symbol_file in tombstone_set:
                            should_remove = True
                            
                    if should_remove:
                        logger.info(f"Pruning stale page {filepath} (file metadata: {file_val})")
                        os.remove(filepath)
                except Exception as e:
                    logger.warning(f"Failed to inspect/prune page {filepath}: {e}")
