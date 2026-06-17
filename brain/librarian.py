import os
from datetime import datetime
import yaml
import json
import time
import re
from typing import Dict, Any, List, Optional, Set
from contextlib import contextmanager
from brain.logger import get_logger

logger = get_logger(__name__)

class LibrarianEngine:
    """
    Production-grade Obsidian vault population engine.
    """
    def __init__(self, repo_path: str, vault_path: str, indexer=None):
        self.repo_path = os.path.abspath(repo_path)
        self.vault_path = os.path.abspath(vault_path)
        self.indexer = indexer
        self.last_sync = datetime.now()
        os.makedirs(self.vault_path, exist_ok=True)
        self.lock_file = os.path.join(self.repo_path, ".qbrain.lock")

    @contextmanager
    def lock(self, timeout: float = 30.0, retry_interval: float = 1.0):
        start_time = time.time()
        acquired = False
        while time.time() - start_time < timeout:
            try:
                with open(self.lock_file, "x") as f: f.write(json.dumps({"pid": os.getpid(), "create_time": time.time()}))
                acquired = True; break
            except FileExistsError:
                if self._is_lock_stale(): self._force_release_lock(); continue
                time.sleep(retry_interval)
        if not acquired: raise RuntimeError("Failed to acquire lock")
        try: yield
        finally: self._force_release_lock()

    def _is_lock_stale(self) -> bool:
        if not os.path.exists(self.lock_file): return True
        try:
            with open(self.lock_file, "r") as f: pid = json.loads(f.read().strip()).get("pid")
            if pid == os.getpid(): return False
            if os.name == "nt":
                import ctypes; h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if h: ctypes.windll.kernel32.CloseHandle(h); return False
                return True
            else:
                try: os.kill(pid, 0); return False
                except OSError: return True
        except Exception: return True

    def _force_release_lock(self):
        if os.path.exists(self.lock_file):
            try: os.remove(self.lock_file)
            except Exception: pass

    def setup_vault(self):
        dirs = ["symbols", "files", "behaviors", "changes", "changes/recent", "changes/archive", "rules", "narratives"]
        for d in dirs: os.makedirs(os.path.join(self.vault_path, d), exist_ok=True)
        bp = os.path.join(self.vault_path, "baseline.md")
        if not os.path.exists(bp):
            with open(bp, "w", encoding="utf-8") as f: f.write("# Qbrain Baseline\n")

    def _get_safe_filename(self, name: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
        if len(safe) > 60:
            import hashlib; h = hashlib.md5(name.encode()).hexdigest()[:6]
            return f"{safe[:50]}_{h}"
        return safe

    def _sanitize_for_table(self, text: str) -> str:
        if not text: return "—"
        return str(text).replace("\n", "<br>").replace("|", "\\|")

    def _get_semantic_state_label(self, state: str) -> str:
        if not state: return "unknown"
        clean = state.strip()
        sinks = {
            "header": "📁 Redirect", 
            "mysqli_query": "Query", 
            "mysqli_connect": "Connect", 
            "eval": "🚨 EVAL", 
            "exec": "🚨 EXEC", 
            "system": "🚨 SYSTEM",
            "shell_exec": "🚨 SHELL", 
            "define": "⚙️ DEF", 
            "include": "📁 INC", 
            "require": "📁 REQ", 
            "include_once": "📁 INC-1", 
            "require_once": "📁 REQ-1"
        }
        
        if clean.startswith("[") and "]" in clean:
            parts = clean.split("]", 1)
            verb, content = parts[0][1:].lower(), parts[1].strip()
            
            # Special handling for cookie/session context
            prefix = ""
            if "cookie" in content.lower(): prefix = "🍪 "
            elif "session" in content.lower(): prefix = "🆔 "
            elif "security" in content.lower() or "level" in content.lower(): prefix = "🔍 "
            
            if "startup" in verb or "init" in verb: prefix += "🛡️ "
            if "render" in verb or "echo" in verb or "print" in verb: prefix += "🖥️ "
            if "db" in verb or "query" in verb or "mysqli" in verb or "pdo" in verb or "sql" in verb: prefix += "[(DB)] "
            
            label = sinks.get(verb, verb.upper())
            disp = re.sub(r"['\"\s]", "", content)
            if len(disp) > 40: disp = disp[:37] + "..."
            
            full_label = f"{label}: {disp}" if disp else label
            return prefix + full_label
            
        low = clean.lower()
        if low in sinks: return sinks[low]
        
        return clean.split("/")[-1] if "/" in clean else clean

    def _safe_path(self, subdir: str, filename: str) -> str:
        target = os.path.abspath(os.path.join(self.vault_path, subdir, filename))
        if not target.startswith(self.vault_path): raise ValueError(f"Path traversal risk")
        return target

    def export_symbol(self, sd: dict, subdirectory: str = ""):
        name = sd.get("name")
        if not name: return
        safe_name = self._get_safe_filename(name)
        dir_p = os.path.join(self.vault_path, "symbols", subdirectory)
        os.makedirs(dir_p, exist_ok=True); filepath = os.path.join(dir_p, f"{safe_name}.md")
        kind = sd.get("kind", "Function")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump({"type": "symbol", "kind": kind, "name": name, "language": sd.get("language"), "file": sd.get("file"), "signature": sd.get("signature"), "mass": sd.get("mass"), "potential_energy": sd.get("potential_energy"), "archetype": sd.get("archetype"), "line": sd.get("line"), "line_range": sd.get("line_range")}, f, default_flow_style=False)
            f.write("---\n\n# " + {"Class":"🏛️","Interface":"🔌","Enum":"📜","Variable":"💎","Module":"📦","Method":"⚡","Function":"λ"}.get(kind, "🔧") + " " + kind + ": " + name + "\n\n")
            if sd.get("docstring"): f.write(f"> {sd['docstring'].strip()}\n\n")
            if sd.get("line") is not None: f.write(f"**Line:** {sd.get('line')}\n\n")
            members = sd.get("members", [])
            if members:
                f.write("## Members\n| Member | Kind | Signature |\n|:---|:---|:---|\n")
                for m in members: f.write(f"| [[{m.get('name')}]] | `{m.get('kind','Method')}` | `{m.get('signature') or m.get('name')}` |\n")
            vs = sd.get("variable_states", {})
            if vs:
                f.write("\n## Data Model & Constraints\n| Variable | Type | State | Details |\n|:---|:---|:---|:---|\n")
                for v, d in vs.items():
                    dtl = [f"prop `{p}` ({pd.get('type')})" for p, pd in d.get("properties", {}).items()] + [f"check `{c}`" for c in list(set(d.get("constraints", [])))]
                    f.write(f"| `{v}` | `{d.get('type','unknown')}` | `{d.get('state','CONSTANT')}` | {', '.join(dtl) if dtl else '—'} |\n")
            fp = sd.get("flow_paths", [])
            if fp:
                f.write("\n## Dataflow Graph\n```mermaid\ngraph LR\n")
                for i, p in enumerate(fp):
                    src, snk, var, st, vt = [str(p.get(k, "unknown")).replace('"',"'") for k in ["source", "sink", "variable", "state", "type"]]
                    lbl = f"{var}:{vt} ({st})" if vt else f"{var} ({st})"
                    if len(lbl) > 100: lbl = lbl[:97] + "..."
                    f.write(f'  P{i}_SRC["{src}"] -- "{lbl}" --> P{i}_SINK["{snk}"]\n')
                f.write("```\n")
            callers, callees = sd.get("callers", []), sd.get("callees", [])
            if callers: f.write("\n## Entanglements\n### Inbound Callers\n" + "\n".join([f"- `[[{c}]]`" for c in callers]) + "\n")
            if callees: f.write("### Outbound Callees\n" + "\n".join([f"- `[[{c}]]`" for c in callees]) + "\n")
            if sd.get("business_rules"): f.write("\n## Business Rules\n" + "\n".join([f"- {r}" for r in sd["business_rules"]]) + "\n")
            if sd.get("vulnerabilities"): f.write("\n## Security Findings\n" + "\n".join([f"- **{v.get('severity','LOW')}**: {v.get('message') or v.get('description')}" for v in sd["vulnerabilities"]]) + "\n")
            snippet = sd.get("code_snippet")
            if snippet and not snippet.startswith("[Full file context"): f.write(f"\n## Implementation\n```{sd.get('language','generic')}\n{snippet}\n```\n")

    def export_file(self, fd: dict):
        fp = fd.get("file_path")
        if not fp: return
        filepath = self._safe_path("files", f"{self._get_safe_filename(fp)}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(fd, f, default_flow_style=False)
            f.write("---\n\n# File: " + fp + "\n\n## Metadata\n- **Language:** " + str(fd.get('language')) + "\n- **Lines of Code:** " + str(fd.get('lines_of_code')) + "\n- **Size:** " + str(fd.get('size')) + " bytes\n\n")
            fvs = fd.get("variable_states", {})
            if fvs:
                f.write("## File-Level Data Model\n| Variable | Type | State |\n|:---|:---|:---|\n")
                for v, d in fvs.items(): f.write(f"| `{v}` | `{d.get('type','unknown')}` | `{d.get('state','CONSTANT')}` |\n")
            sd = fd.get("symbols_data", [])
            if sd:
                f.write("\n## Symbols and Logic\n| Symbol | Kind | Line | Signature | Description |\n|:---|:---|:---|:---|:---|\n")
                for s in sd: f.write(f"| [[{s.get('name')}]] | `{s.get('kind','Function')}` | {s.get('line','—')} | `{s.get('signature') or s.get('name')}` | {(s.get('docstring') or '').split('\\n')[0]} |\n")
                f.write("\n## Business Logic & Requirements\n")
                for s in sd:
                    for r in s.get("business_rules", []): f.write(f"- **{s.get('name')}**: {r}\n")
                f.write("\n## Dataflow & Taint Summary\n| Source | Line | Variable | State | Constraints | Sink |\n|:---|:---|:---|:---|:---|:---|\n")
                for s in sd:
                    for p in s.get("flow_paths", []):
                        cs = ", ".join(p.get("constraints", [])) if p.get("constraints") else "—"
                        f.write(f"| [[{s.get('name')}]] | {s.get('line','—')} | `{p.get('variable')}` | `{p.get('state')}` | `{cs}` | `{p.get('sink') or 'internal'}` |\n")
            syms = fd.get("symbols", [])
            if syms: f.write("\n## Navigation\n" + "\n".join([f"- [[{s}]]" for s in syms]) + "\n")

    def _make_transition_label(self, clr: str, cle: str, funcs: List[dict], sm: dict) -> str:
        caller = next((f for f in funcs if f.get("name") == clr), None)
        if caller:
            passed, cl_b, decision_drivers = [], cle.split(".")[-1], []
            for fl in caller.get("flow_paths", []):
                v = fl.get("variable", "")
                # Detect decision drivers (Cookie, Session, Security levels)
                if any(x in v for x in ["$_COOKIE", "$_SESSION", "security", "level", "admin"]):
                    decision_drivers.append(f"{v}:{fl.get('state','?')}")
                
                if fl.get("sink") and (fl["sink"] == cle or fl["sink"] == cl_b):
                    passed.append(f"{v}:{fl.get('state','?')}")
            
            if decision_drivers:
                drivers_str = ", ".join(list(set(decision_drivers)))
                if len(drivers_str) > 50: drivers_str = drivers_str[:47] + "..."
                return f"[Scenario: {drivers_str}]"
            
            if passed:
                p_str = ", ".join(list(set(passed)))
                if len(p_str) > 50: p_str = p_str[:47] + "..."
                return p_str
                
        meta = sm.get(cle, {})
        p = (meta.get("params") or [{"name":""}])[0].get("name") or ""
        r = "→" + str(meta.get("returns", {}).get("type", "")) if meta.get("returns") else ""
        return f"{p}{r}"

    def generate_behavior_model(self, ep_f: str, ep_p: str, cm: dict, funcs: List[dict], sm: dict, max_d: int = 10, max_s: int = 50) -> dict:
        states, trans, visited = {ep_f}, [], {ep_f}
        detailed = cm.get(ep_f, {}).get("callees_detailed", [])
        queue = [(c, ep_f, 1, cond) for c, cond in detailed] if detailed else [(c, ep_f, 1, None) for c in cm.get(ep_f, {}).get("callees", []).copy()]
        while queue:
            if len(states) >= max_s: break
            curr, par, dep, sl = queue.pop(0); states.add(curr); can = curr
            if curr.startswith("[") and "]" in curr:
                hint = curr.split("]", 1)[1].strip().replace("{","").replace("}","").strip("'\" /")
                for f in funcs:
                    fn = f.get("name", "")
                    if hint == fn or fn.endswith(hint) or hint.endswith(fn): can = fn; break
            lbl = sl or self._make_transition_label(par, curr, funcs, sm)
            if lbl and "[Scenario:" in lbl:
                txt = lbl.replace("[Scenario: ", "").rsplit("]", 1)[0].strip(); node = f"Decision: {txt}"
                states.add(node); trans.append({"from": par, "to": node}); trans.append({"from": node, "to": curr})
            else: trans.append({"from": par, "to": curr, "condition": lbl or None})
            if dep < max_d and can not in visited:
                visited.add(can); det_next = cm.get(can, {}).get("callees_detailed", [])
                if det_next:
                    for nc, cond in det_next: queue.append((nc, curr, dep + 1, cond))
                else:
                    for nc in cm.get(can, {}).get("callees", []): queue.append((nc, curr, dep + 1, None))
        bm = {}
        for s in states:
            m = sm.get(s)
            if not m:
                # Try to find the symbol in funcs if not in state_meta
                f_m = next((f for f in funcs if f.get("name") == s), None)
                if f_m:
                    ff = f_m.get("file", "").lower()
                    # Deterministic Archetypes
                    if any(x in ff for x in ["db/", "model/", "repository/", "database"]): arch = "data-repository"
                    elif any(x in ff for x in ["api/", "controller/", "service/"]): arch = "api-endpoint"
                    elif any(x in ff for x in ["security", "auth", "guard", "login"]): arch = "security-guard"
                    elif any(x in ff for x in ["util", "helper", "lib/"]): arch = "utility"
                    else: arch = "generic"
                    
                    m = {
                        "params": f_m.get("params", []), 
                        "returns": f_m.get("returns", {}), 
                        "docstring": f_m.get("docstring", ""), 
                        "potential_energy": 0.0, 
                        "archetype": arch, 
                        "variable_states": f_m.get("variable_states", {}), 
                        "flow_paths": f_m.get("flow_paths", []),
                        "line": f_m.get("line", "—")
                    }
            
            if s.startswith("["):
                m = m or {"params": [], "returns": {}, "docstring": "", "variable_states": {}, "flow_paths": [], "archetype": "unknown", "line": "—"}
                # Refine archetypes for sinks
                if "include" in s or "require" in s: 
                    m["archetype"] = "dynamic-include"
                elif any(x in s.lower() for x in ["eval", "exec", "system", "shell_exec", "passthru"]):
                    m["archetype"] = "security-risk"
                elif any(x in s.lower() for x in ["mysqli", "pdo", "sql", "query"]):
                    m["archetype"] = "db-interaction"
                else:
                    m["archetype"] = "data-sink"
            
            bm[s] = m or {"params": [], "returns": {}, "docstring": "", "variable_states": {}, "flow_paths": [], "archetype": "generic", "line": "—"}
        
        return {
            "name": f"{ep_p}-flow", 
            "entrypoint": ep_f, 
            "states": list(states), 
            "transitions": trans, 
            "state_meta": bm, 
            "is_macro_map": bm.get(ep_f, {}).get("archetype") == "system-hub"
        }

    def export_behavior(self, bd: dict):
        name = bd.get("name")
        if not name: return
        fp = self._safe_path("behaviors", f"{self._get_safe_filename(name)}.md")
        sts, trs = bd.get("states", []), bd.get("transitions", [])
        
        with open(fp, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump({
                "type": "behavior", 
                "name": name, 
                "entrypoint": bd.get("entrypoint"), 
                "state_count": len(sts), 
                "transition_count": len(trs)
            }, f, default_flow_style=False)
            f.write("---\n\n# Behavior: " + name + "\n\n")
            
            f.write("## " + ("Macro System Map" if bd.get("is_macro_map") else "State Machine") + "\n\n")
            f.write("```mermaid\ngraph TD\n")
            
            if bd.get("is_macro_map"):
                f.write(f'  {self._get_safe_filename(bd["entrypoint"])}["{bd["entrypoint"]}"]:::hub\n')
                f.write('  classDef hub fill:#f96,stroke:#333,stroke-width:4px;\n')
            
            als = {s: self._get_safe_filename(s) for s in sts}
            for s, al in als.items():
                ss = self._get_semantic_state_label(s).replace('"', "'")
                if s.startswith("Decision:"):
                    f.write(f'    {al}{{{ss}}}\n')
                else:
                    f.write(f'    {al}["{ss}"]\n')
            
            for t in trs:
                frm, to, cnd = als.get(t["from"], t["from"]), als.get(t["to"], t["to"]), t.get("condition")
                if cnd:
                    sc = str(cnd).replace("\n", " ").replace('"', "'")
                    if len(sc) > 100: sc = sc[:97] + "..."
                    f.write(f'    {frm} -- "{sc}" --> {to}\n')
                else:
                    f.write(f"    {frm} --> {to}\n")
            f.write("```\n\n## State Context\n\n| State | Line | PE | Archetype | Summary |\n| :--- | :--- | ---: | :--- | :--- |\n")
            
            m = bd.get("state_meta", {})
            for s in sts:
                sm = m.get(s, {})
                f.write(f"| `[[{s}]]` | {sm.get('line','—')} | {sm.get('potential_energy','—')} | {sm.get('archetype','—')} | {(sm.get('docstring','') or '').split('\\n')[0][:100]} |\n")
            
            f.write("\n" + self._generate_dataflow_narrative(bd))

    def _generate_dataflow_narrative(self, bd: dict) -> str:
        narrative, meta = "## Dataflow Narrative\n\n", bd.get("state_meta", {})
        sources, sinks = [], []
        
        for name, m in meta.items():
            for fl in m.get("flow_paths", []):
                v, src = fl.get("variable", ""), fl.get("source", "")
                if any(x in v or x in src for x in ["$_GET", "$_POST", "$_COOKIE", "$_SESSION", "$_REQUEST"]):
                    sources.append({"name": name, "variable": v, "state": fl.get("state"), "source": src})
                
                snk = fl.get("sink")
                if snk or m.get("archetype") in ["security-risk", "db-interaction", "dynamic-include"]:
                    sinks.append({"name": name, "variable": v, "sink": snk or name, "constraints": fl.get("constraints", [])})
        
        if not sources: return narrative + "No external data sources detected.\n\n"
        
        narrative += "### Detected External Sources\n"
        seen_srcs = set()
        for src in sources:
            line = f"- **{src['variable']}** (via `{src['source']}`) enters at `[[{src['name']}]]` [State: `{src['state']}`]"
            if line not in seen_srcs:
                narrative += line + "\n"
                seen_srcs.add(line)
        
        narrative += "\n### Potential Impact Paths\n"
        impact_count = 0
        for src in sources:
            for snk in sinks:
                if src['variable'] == snk['variable'] or src['name'] == snk['name']:
                    cns = f" with constraints `{', '.join(snk['constraints'])}`" if snk['constraints'] else ""
                    narrative += f"- Data from **{src['variable']}** reaches sink **{snk['sink']}** at `[[{snk['name']}]]`{cns}.\n"
                    impact_count += 1
        
        if impact_count == 0:
            narrative += "No direct taint paths identified in current scope.\n"
            
        if sources and sinks and self.indexer:
            try:
                traces = []
                for src in sources:
                    res = self.indexer.trace_path(function_name=src['name'], direction="outbound", depth=3)
                    for c in res.get("callees", []):
                        if any(s['name'] == c['name'] or s['name'] in c.get('qualified_name','') for s in sinks):
                            traces.append(f"- Trace found: `[[{src['name']}]]` → `{c.get('type','call')}` → `[[{c['name']}]]`")
                
                if traces:
                    narrative += "\n### Verified Dataflow Traces\n"
                    for t in list(set(traces))[:10]:
                        narrative += t + "\n"
            except Exception as e:
                logger.warning(f"Trace path failed in narrative generation: {e}")
                
        return narrative + "\n"

    def export_branch_diff(self, d: dict):
        filepath = self._safe_path("changes", "branch_diff.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# 🌿 Branch Diff & Semantic Distance Report\n\n**Comparing current workspace against:** `{d.get('branch_y', 'main')}`\n\n## 📝 Added Files\n" + "\n".join([f"- {fl}" for fl in d.get("added_files", [])]) + "\n\n## 📝 Semantic Changes\n| File | Distance | Status |\n|:---|:---|:---|\n")
            for sc in d.get("semantic_changes", []): f.write(f"| {sc['file']} | {sc['distance']:.2f} | {sc['status']} |\n")
    def export_warnings(self, ws: List[dict]):
        filepath = self._safe_path("rules", "warnings.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Docstring & Quality Invariants Warnings\n\n| Symbol | File | Warnings |\n|:---|:---|:---|\n")
            for w in ws: f.write(f"| `[[{w['name']}]]` | {w['file']} | {', '.join(w['warnings'])} |\n")

    def export_vulnerabilities(self, vs: List[dict]):
        filepath = self._safe_path("rules", "vulnerabilities.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🛡️ Codebase Security Vulnerabilities\n\n| Severity | Symbol | File | Finding |\n|:---|:---|:---|:---|\n")
            for v in vs: f.write(f"| {v.get('severity','LOW')} | `[[{v.get('safe_link') or self._get_safe_filename(v.get('name') or v.get('function') or 'unknown')}]]` | {v.get('file', 'unknown')} | {v.get('message') or v.get('description', 'unknown')} |\n")

    def export_hotspots(self, hs: dict):
        filepath = self._safe_path("rules", "hotspots.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 📊 Codebase Cognitive & Complexity Hotspots\n\n## 🏋️ Complexity Hotspots (Highest Mass)\n| Symbol | File | Mass | Archetype |\n|:---|:---|:---|:---|\n")
            for h in hs.get("complexity", []): f.write(f"| `[[{h['name']}]]` | {h.get('file', 'unknown')} | {h['mass']:.1f} | {h.get('archetype', '—')} |\n")
            f.write("\n## ⚡ Attention Hotspots\n| Symbol | File | PE | Archetype |\n|:---|:---|:---|:---|\n")
            for h in hs.get("attention", []): f.write(f"| `[[{h['name']}]]` | {h.get('file', 'unknown')} | {h['potential_energy']:.2f} | {h.get('archetype', '—')} |\n")

    def export_archetypes(self, gs: dict):
        filepath = self._safe_path("rules", "archetypes.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# 🧩 Codebase Semantic Archetypes\n\n")
            for arch, syms in gs.items():
                f.write(f"## {'-'.join([w.capitalize() for w in arch.split('-')])} (Narrative: [[archetype_{self._get_safe_filename(arch)}]])\n")
                for s in syms[:15]: f.write(f"- `[[{s['name']}]]`{(' (Confidence: ' + str(s['confidence'] * 100) + '%)' if 'confidence' in s else '')}\n")
                f.write("\n")