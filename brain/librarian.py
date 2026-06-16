import os
import yaml
import json
import time
import re
import subprocess
from typing import Dict, Any, List, Optional, Set
from contextlib import contextmanager
from brain.logger import get_logger

logger = get_logger(__name__)

class LibrarianEngine:
    """
    Knowledge synchronizer between the memory graph and Obsidian vault.
    """
    def __init__(self, repo_path: str, vault_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self.vault_path = os.path.abspath(vault_path)
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
                        return True  # Invalid PID format, treat as stale
            
            if pid == os.getpid():
                return False  # Current process is active, not stale
            
            if os.name == "nt":
                import ctypes
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                kernel32 = ctypes.windll.kernel32
                kernel32.OpenProcess.restype = ctypes.c_void_p
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if handle:
                    kernel32.CloseHandle(ctypes.c_void_p(handle))
                    return False  # process is running, lock is not stale
                err = kernel32.GetLastError()
                if err == 5:  # Access Denied means running
                    return False
                return True   # not running, stale
            else:
                try:
                    os.kill(pid, 0)
                    return False  # process is running, lock is not stale
                except OSError as e:
                    import errno
                    if e.errno == errno.ESRCH:
                        return True
                    return False  # e.g. permission error means process is running
        except PermissionError:
            # If locked/busy, the process is active, lock is NOT stale
            return False
        except Exception:
            return True

    def _force_release_lock(self):
        if os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except Exception:
                pass

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
        return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)

    def _safe_path(self, subdir: str, filename: str) -> str:
        """Sanitize path and ensure it's inside the vault."""
        target = os.path.abspath(os.path.join(self.vault_path, subdir, filename))
        if not target.startswith(self.vault_path):
            raise ValueError(f"Path traversal detected (Security Risk): {target}")
        return target

    def export_symbol(self, symbol_data: dict):
        name = symbol_data.get("name")
        if not name:
            return
        if ".." in name or name.startswith("/") or name.startswith("\\"):
            raise ValueError("Path traversal detected (Security Risk) in symbol name")
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
        
        # Determine header badge
        badge = "🔧"
        if kind == "Class":
            badge = "🏛️"
        elif kind == "Interface":
            badge = "📑"
        elif kind == "Enum":
            badge = "🗳️"
        elif kind == "Variable":
            badge = "📌"
        elif kind == "Module":
            badge = "📦"
        elif kind == "Method":
            badge = "⚡"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(frontmatter, f, default_flow_style=False)
            f.write("---\n\n")
            f.write(f"# {badge} {kind}: {name}\n\n")
            if symbol_data.get("line") is not None:
                f.write(f"**Line:** {symbol_data.get('line')}\n\n")
            if symbol_data.get("docstring"):
                f.write(f"## Documentation\n{symbol_data.get('docstring')}\n\n")
            
            # Data Model & Constraints
            var_states = symbol_data.get("variable_states", {})
            flow_paths = symbol_data.get("flow_paths", [])
            
            if var_states:
                f.write("## Data Model & Constraints\n")
                f.write("| Variable | Type | State | Properties / Constraints |\n")
                f.write("|:---|:---|:---|:---|\n")
                for var, data in var_states.items():
                    state = data.get("state", "CONSTANT")
                    vtype = data.get("type", "unknown")
                    
                    details = []
                    props = data.get("properties", {})
                    for p, pdata in props.items():
                        details.append(f"prop `{p}` ({pdata.get('type')})")
                    
                    constraints = data.get("constraints", [])
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
                    label = f"{var}:{vtype} ({state})" if vtype else f"{var} ({state})"
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
                    f.write(f"- `[[{neighbor}]]` ({sim * 100:.1f}% similarity)\n")
                f.write("\n")
            
            callers = symbol_data.get("callers", [])
            callees = symbol_data.get("callees", [])
            if callers or callees:
                f.write("## Entanglements\n")
                if callers:
                    f.write("### Inbound Callers\n")
                    for caller in callers:
                        f.write(f"- `[[{caller}]]` \n")
                if callees:
                    f.write("### Outbound Callees\n")
                    for callee in callees:
                        f.write(f"- `[[{callee}]]` \n")
                f.write("\n")
                
            if symbol_data.get("business_rules"):
                f.write("## Business Rules\n")
                for rule in symbol_data.get("business_rules", []):
                    f.write(f"- {rule}\n")
                f.write("\n")

            if symbol_data.get("vulnerabilities"):
                f.write("## Security Findings\n")
                for vuln in symbol_data.get("vulnerabilities", []):
                    # For symbol findings, we use message
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
        if not file_path:
            return
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
            f.write("\n")

            var_states = file_data.get("variable_states", {})
            if var_states:
                f.write("## File-Level Data Model\n")
                f.write("| Variable | Type | State |\n")
                f.write("|:---|:---|:---|\n")
                for var, data in var_states.items():
                    f.write(f"| `{var}` | `{data.get('type', 'unknown')}` | `{data.get('state', 'CONSTANT')}` |\n")
                f.write("\n")

            symbols = file_data.get("symbols", [])
            if symbols:
                f.write("## Symbols Defined\n")
                for s in symbols:
                    f.write(f"- [[{s}]]\n")
                f.write("\n")

    def _make_transition_label(self, caller_name: str, callee_name: str, funcs: List[dict], sym_meta: dict) -> str:
        """Generates a transition label based on dataflow or signature."""
        caller_obj = next((f for f in funcs if f.get("name") == caller_name), None)
        if caller_obj:
            passed_vars = []
            callee_base = callee_name.split(".")[-1]
            for flow in caller_obj.get("flow_paths", []):
                sink = flow.get("sink", "")
                if sink and (sink == callee_name or sink == callee_base):
                    passed_vars.append(f"{flow.get('variable')}:{flow.get('state')}")
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
            if rtype:
                parts.append(f"→{rtype}")
        return ", ".join(parts) if parts else ""

    def generate_behavior_model(
        self, 
        entrypoint_func: str, 
        entrypoint_path: str,
        calls_map: dict, 
        funcs: List[dict], 
        sym_meta: dict,
        max_depth: int = 10,
        max_states: int = 50
    ) -> dict:
        """
        Builds a macroscopic behavioral model from an entrypoint.
        """
        callees_from_map = calls_map.get(entrypoint_func, {}).get("callees", [])
        
        states: set = {entrypoint_func}
        transitions = []
        visited: set = {entrypoint_func}
        queue = [(c, entrypoint_func, 1) for c in callees_from_map]
        
        while queue:
            if len(states) >= max_states:
                break
            current, parent, depth = queue.pop(0)
            states.add(current)
            label = self._make_transition_label(parent, current, funcs, sym_meta)
            transitions.append({"from": parent, "to": current, "condition": label or None})
            if depth < max_depth and current not in visited:
                visited.add(current)
                next_callees = calls_map.get(current, {}).get("callees", [])
                for nc in next_callees:
                    if nc not in visited:
                        queue.append((nc, current, depth + 1))

        built_state_meta = {}
        for s in states:
            meta = sym_meta.get(s)
            if not meta:
                f_match = next((f for f in funcs if f.get("name") == s), None)
                if f_match:
                    meta = {
                        "params": f_match.get("params", []),
                        "returns": f_match.get("returns", {}),
                        "docstring": f_match.get("docstring", ""),
                        "potential_energy": 0.0,
                        "archetype": "generic",
                        "variable_states": f_match.get("variable_states", {})
                    }
            built_state_meta[s] = meta or {"params": [], "returns": {}, "docstring": "", "variable_states": {}}

        is_hub = built_state_meta.get(entrypoint_func, {}).get("archetype") == "system-hub"

        return {
            "name": f"{entrypoint_path}-flow",
            "entrypoint": entrypoint_func,
            "states": list(states),
            "transitions": transitions,
            "state_meta": built_state_meta,
            "is_macro_map": is_hub
        }

    def export_behavior(self, behavior_data: dict):
        name = behavior_data.get("name")
        if not name:
            return
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
                    if alias == s:
                        f.write(f"    {s}\n")
                    else:
                        f.write(f'    state "{s}" as {alias}\n')
                state_aliases[s] = alias
                
            for t in transitions:
                frm = state_aliases.get(t["from"], t["from"])
                to = state_aliases.get(t["to"], t["to"])
                cond = t.get("condition")
                if is_macro:
                    if cond:
                        f.write(f'  {frm} -- "{cond}" --> {to}\n')
                    else:
                        f.write(f"  {frm} --> {to}\n")
                else:
                    if cond:
                        safe_cond = str(cond).replace("\n", " ").replace('"', "'")
                        f.write(f"    {frm} --> {to}: {safe_cond}\n")
                    else:
                        f.write(f"    {frm} --> {to}\n")
            f.write("```\n\n")
            
            f.write("## State Context\n\n")
            f.write("| State | PE | Archetype | Params | Returns | Summary |\n")
            f.write("| :--- | ---: | :--- | :--- | :--- | :--- |\n")
            meta = behavior_data.get("state_meta", {})
            for s in states:
                s_meta = meta.get(s, {})
                pe = s_meta.get("potential_energy", "—")
                arch = s_meta.get("archetype", "—")
                v_states = s_meta.get("variable_states", {})
                invariants = []
                for v, vdata in v_states.items():
                    if isinstance(vdata, dict) and vdata.get("constraints"):
                        invariants.extend(vdata["constraints"])
                invariants_str = "<br>".join(list(set(invariants))[:3]) if invariants else "—"
                p = s_meta.get("params", [])
                params_str = ", ".join([str(x) for x in p]) if p else "—"
                r = s_meta.get("returns", "—")
                doc = s_meta.get("docstring", "")
                summary = doc.split("\n")[0][:100] if doc else "—"
                f.write(f"| `[[{s}]]` | {pe} | {arch} | {params_str} | `{r}` | {summary} <br> **Invariants:** {invariants_str} |\n")
            f.write("\n")

    def export_narrative(self, archetype: str, symbols: List[dict]):
        """Exports a high-level narrative summary of a subsystem."""
        safe_arch = self._get_safe_filename(archetype)
        filepath = self._safe_path("narratives", f"archetype_{safe_arch}.md")
        total_mass = sum(s.get("mass", 1.0) for s in symbols)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Subsystem Narrative: {archetype}\n\n")
            f.write(f"This subsystem contains {len(symbols)} symbols with a collective mass of {total_mass:.2f}.\n\n")
            f.write(f"## Key Symbols\n")
            key_symbols = sorted(symbols, key=lambda x: x.get("mass", 0), reverse=True)[:10]
            for s in key_symbols:
                f.write(f"- `[[{s['name']}]]` (Mass: {s.get('mass', 0):.2f}, PE: {s.get('potential_energy', 0):.2f})\n")
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
            for w in warnings:
                f.write(f"| `[[{w['name']}]]` | {w['file']} | {', '.join(w['warnings'])} |\n")

    def export_vulnerabilities(self, vulns: List[dict]):
        filepath = self._safe_path("rules", "vulnerabilities.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🛡️ Codebase Security Vulnerabilities\n\n")
            f.write("| Severity | Symbol | File | Finding |\n")
            f.write("|:---|:---|:---|:---|\n")
            for v in vulns:
                severity = v.get("severity", "LOW")
                name = v.get("name") or v.get("function") or "unknown"
                safe_link = v.get("safe_link") or self._get_safe_filename(name)
                file_path = v.get("file") or "unknown"
                finding = v.get("message") or v.get("description") or "unknown"
                f.write(f"| {severity} | `[[{safe_link}]]` | {file_path} | {finding} |\n")

    def export_hotspots(self, hotspots: dict):
        filepath = self._safe_path("rules", "hotspots.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 📊 Codebase Cognitive & Complexity Hotspots\n\n")
            f.write("## 🏋️ Complexity Hotspots (Highest Mass)\n")
            f.write("| Symbol | File | Mass | Archetype |\n")
            f.write("|:---|:---|:---|:---|\n")
            for h in hotspots.get("complexity", []):
                f.write(f"| `[[{h['name']}]]` | {h.get('file', 'unknown')} | {h['mass']:.1f} | {h.get('archetype', '—')} |\n")
            
            f.write("\n## ⚡ Attention Hotspots (Highest Drift / Attention Debt)\n")
            f.write("| Symbol | File | Potential Energy | Archetype |\n")
            f.write("|:---|:---|:---|:---|\n")
            for h in hotspots.get("attention", []):
                f.write(f"| `[[{h['name']}]]` | {h.get('file', 'unknown')} | {h['potential_energy']:.2f} | {h.get('archetype', '—')} |\n")

    def export_archetypes(self, groups: dict):
        filepath = self._safe_path("rules", "archetypes.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🧩 Codebase Semantic Archetypes\n\n")
            for arch, symbols in groups.items():
                title_arch = "-".join([w.capitalize() for w in arch.split("-")])
                safe_arch = self._get_safe_filename(arch)
                f.write(f"## {title_arch} (Narrative: [[archetype_{safe_arch}]])\n")
                for s in symbols[:15]:
                    confidence_str = f" (Confidence: {s['confidence']:.2%})" if 'confidence' in s else ""
                    f.write(f"- `[[{s['name']}]]`{confidence_str}\n")
                f.write("\n")

    def export_branch_diff(self, diff: dict):
        filepath = self._safe_path("changes", "branch_diff.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🌿 Branch Diff & Semantic Distance Report\n\n")
            target = diff.get("target_branch") or "main"
            f.write(f"**Comparing current workspace against:** `{target}`\n\n")
            distance = diff.get("semantic_distance", 0.0)
            f.write(f"**Semantic Distance:** `{distance}`\n\n")
            
            f.write("## 📝 Modified Files & Relevance Scores\n")
            f.write("| File | Status | Churn | Relevance |\n")
            f.write("|:---|:---|:---|:---|\n")
            for fl in diff.get("files", []):
                f.write(f"| {fl['file']} | {fl.get('status')} | {fl.get('churn')} | {fl.get('relevance_score')} |\n")
