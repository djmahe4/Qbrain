import os
import typer
import re
import logging
from brain.librarian import LibrarianEngine
from brain.docstring_parser import DocstringParser
from brain.vuln_scanner import VulnerabilityScanner
from brain.systemic_auditor import SystemicAuditor
from brain.entrypoint_finder import EntrypointFinder
from brain.branch_diff import BranchDiff
from brain.embedder import Embedder
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.dataflow_engine import DataFlowEngine
from brain.language_parser import detect_language

logger = logging.getLogger(__name__)

def sync_library(config, indexer, console):
    repo_path = config.repo_path
    vault_path = config.data.get("vault_path", os.path.join(repo_path, "obsidian_vault"))
    
    console.print(f"Syncing librarian from repository [cyan]{repo_path}[/cyan] to vault [cyan]{vault_path}[/cyan]...")
    
    embedder = Embedder()
    engine = LibrarianEngine(repo_path, vault_path, indexer=indexer)
    branch_diff = BranchDiff(config, embedder)
    
    try:
        with engine.lock():
            engine.setup_vault()
            
            # 1. Load cognitive data
            console.print("Loading cognitive properties (merging Graph and SQLite)...")
            cognitive_info = {}
            try:
                cog_res = indexer.query_graph(
                    "MATCH (f) WHERE f:Function OR f:Method OR f:Module OR f:Class OR f:Interface OR f:Enum "
                    "RETURN f.name AS name, f.mass AS mass, f.potential_energy AS potential_energy, f.semantic_archetype AS archetype"
                )
                for item in cog_res:
                    name = item.get("name")
                    if name:
                        mass, pe, arch = item.get("mass"), item.get("potential_energy"), item.get("archetype")
                        cognitive_info[name] = {
                            "mass": float(mass) if (mass is not None and str(mass).strip() != "") else 1.0,
                            "potential_energy": float(pe) if (pe is not None and str(pe).strip() != "") else 0.0,
                            "archetype": arch if (arch is not None and str(arch).strip() != "") else "generic"
                        }
            except Exception as e: console.print(f"[yellow]Warning: graph metadata load failed: {e}[/yellow]")

            try:
                for b in indexer.persistence.get_internal_beliefs():
                    name = b.get("symbol")
                    if name:
                        if name not in cognitive_info: cognitive_info[name] = {"mass": b.get("support_mass", 1.0), "potential_energy": b.get("potential_energy", 0.0), "archetype": b.get("winner", "generic")}
                        else:
                            cognitive_info[name]["mass"] = b.get("support_mass", cognitive_info[name]["mass"])
                            cognitive_info[name]["potential_energy"] = b.get("potential_energy", cognitive_info[name]["potential_energy"])
                            cognitive_info[name]["archetype"] = b.get("winner", cognitive_info[name]["archetype"])
            except Exception as e: console.print(f"[yellow]Warning: SQLite beliefs merge failed: {e}[/yellow]")

            _pe_mostly_zero = (sum(1 for v in cognitive_info.values() if v.get("potential_energy", 0.0) == 0.0) / max(len(cognitive_info), 1)) > 0.8 if cognitive_info else True
            
            # 2. CALLS relationships
            console.print("Mapping function entanglements...")
            calls_map = {}
            try:
                for item in indexer.query_graph("MATCH (a)-[:CALLS]->(b) RETURN a.name AS caller, b.name AS callee"):
                    caller, callee = item.get("caller"), item.get("callee")
                    if caller and callee:
                        calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
                        calls_map.setdefault(callee, {}).setdefault("callers", []).append(caller)
            except Exception as e: console.print(f"[yellow]Warning: graph call map failed: {e}[/yellow]")

            # 3. Retrieve and analyze functions
            parser, df_engine = DocstringParser(indexer), DataFlowEngine()
            all_symbols_res = indexer.query_graph("MATCH (n) WHERE n:Function OR n:Method OR n:Module OR n:Class OR n:Interface OR n:Enum RETURN n.name AS name, labels(n) AS labels, COALESCE(n.file_path, n.file) AS file, COALESCE(n.start_line, n.line) AS line, n.end_line AS end_line")
            
            funcs = parser.get_functions_with_docstrings()
            existing_names = {f["name"] for f in funcs}
            _EXC = {".md", ".json", ".txt", ".yaml", ".yml", ".lock", ".log", ".toml"}
            for item in all_symbols_res:
                s_name, f_path = item.get("name"), (item.get("file") or "").lower()
                if s_name and s_name not in existing_names and not any(f_path.endswith(ext) for ext in _EXC):
                    funcs.append({"name": s_name, "file": item.get("file"), "line": item.get("line"), "end_line": item.get("end_line"), "labels": item.get("labels", []), "docstring": "", "language": detect_language(f_path)})

            short_to_qualified, file_symbols_data = {}, {}
            for f in funcs:
                fn, fp = f.get("name", ""), f.get("file", "")
                short_to_qualified[fn.split("/")[-1].split(".")[-1]] = fn
                short_to_qualified[fn] = fn
                if fp:
                    short_to_qualified[fp] = fn
                    file_symbols_data.setdefault(fp, []).append(f)

            file_suffixes = {fp.split("/")[-1]: fp for fp in file_symbols_data.keys()}
            _SKIP = {"yaml", "markdown", "toml", "json", "generic"}
            
            for f in funcs:
                name, f_path, labels = f.get("name"), f.get("file"), f.get("labels", [])
                lang = f.get("language") or detect_language(f_path or "")
                f["language"] = lang
                if lang in _SKIP:
                    f["code_snippet"], f["variable_states"], f["flow_paths"] = "", {}, []
                    continue
                
                if "Module" in labels:
                    full_p = os.path.join(repo_path, f_path) if f_path else ""
                    if full_p and os.path.exists(full_p):
                        try:
                            with open(full_p, "r", encoding="utf-8", errors="ignore") as fo: f["code_snippet"] = fo.read()
                        except Exception: f["code_snippet"] = ""
                    else: f["code_snippet"] = ""
                else:
                    try:
                        snippet_res = indexer.get_code_snippet(name)
                        code = snippet_res.get("code") or ""
                        if not code and f.get("line") and f.get("end_line") and f_path:
                            full_p = os.path.join(repo_path, f_path)
                            if os.path.exists(full_p):
                                with open(full_p, "r", encoding="utf-8", errors="ignore") as fo:
                                    lns = fo.readlines(); start, end = int(f["line"]) - 1, int(f["end_line"])
                                    code = "".join(lns[start:end])
                        f["code_snippet"] = code
                    except Exception: f["code_snippet"] = ""

                df_res = df_engine.analyze_snippet(f["code_snippet"], lang)
                f["variable_states"], f["flow_paths"], f["dataflow"] = df_res.get("variable_states", {}), df_res.get("flow_paths", []), df_res.get("raw_atoms", [])

                for atom in f["dataflow"]:
                    atype = atom.get("type")
                    if atype not in ("synthesized_call", "sink"): continue
                    tnode, verb = None, atom.get("verb") or atom.get("sink")
                    if atype == "synthesized_call":
                        hint = atom.get("resolved_hint")
                        if hint:
                            ch = os.path.normpath(hint.replace("{","").replace("}","").strip("'\" /").replace("\\","/"))
                            if ch in short_to_qualified: tnode = short_to_qualified[ch]
                            else:
                                for sq in short_to_qualified.keys():
                                    sq_norm = os.path.normpath(sq)
                                    if sq_norm.endswith(ch) or ch.endswith(sq_norm) or ch in sq_norm: tnode = short_to_qualified[sq]; break
                                if not tnode:
                                    hb = ch.split("/")[-1]
                                    if hb in file_suffixes: tnode = file_suffixes[hb]
                        ft = tnode or f"[{verb}] {atom.get('raw_path')}"
                    else:
                        sn = atom.get("sink")
                        if sn in short_to_qualified: tnode = short_to_qualified[sn]
                        ft = tnode or f"[{sn}] {atom.get('args', '')}"
                    
                    cond = ", ".join(atom.get("constraints", [])) or None
                    if (ft, cond) not in calls_map.get(name, {}).get("callees_detailed", []):
                        calls_map.setdefault(name, {}).setdefault("callees_detailed", []).append((ft, cond))
                        calls_map.setdefault(name, {}).setdefault("callees", []).append(ft)
                    if name not in calls_map.get(ft, {}).get("callers", []): calls_map.setdefault(ft, {}).setdefault("callers", []).append(name)

            # 4. Neighbors & PE
            semantic_neighbors, _func_embeddings = {}, {}
            try:
                genomes = [DocstringParser.build_genome(f) for f in funcs]
                if genomes:
                    embs = embedder.embed(genomes)
                    for i, f in enumerate(funcs):
                        fn = f.get("name"); _func_embeddings[fn] = embs[i]; sims = []
                        for j, fo in enumerate(funcs):
                            if i != j: sims.append((fo.get("name"), Embedder.cosine_similarity(embs[i], embs[j])))
                        sims.sort(key=lambda x: x[1], reverse=True); semantic_neighbors[fn] = sims[:3]
            except Exception as e: console.print(f"[yellow]Warning: semantic neighbors failed: {e}[/yellow]")

            if _pe_mostly_zero and _func_embeddings:
                console.print("[dim]Computing potential energy inline...[/dim]")
                try:
                    scorer = QuantumScorer(config, indexer); nodes_pe = []
                    for f in funcs:
                        fn, emb = f.get("name"), _func_embeddings.get(f.get("name"))
                        if emb is not None: nodes_pe.append(FunctionNode(name=fn, embedding=emb, complexity=float(f.get("complexity", 1.0) or 1.0), side_effects=float(f.get("sideEffects", 0.0) or 0.0), is_exported=bool(f.get("isExported", False)), file=f.get("file", ""), line=int(f.get("line", 0) or 0)))
                    scorer.run_simulation(nodes_pe, iterations=30)
                    for n in nodes_pe:
                        if n.name in cognitive_info: cognitive_info[n.name]["potential_energy"], cognitive_info[n.name]["archetype"] = n.potential_energy, n.quantum_state
                        else: cognitive_info[n.name] = {"mass": n.mass, "potential_energy": n.potential_energy, "archetype": n.quantum_state}
                    scorer.write_physics_to_graph(nodes_pe)
                except Exception as e: console.print(f"[yellow]Warning: PE computation failed: {e}[/yellow]")

            # 5. security/audits
            vulnerabilities = []
            try:
                rules_list = []
                for f in funcs:
                    for r in parser.parse_genome(f).get("business_rules", []):
                        desc, cat = r.lower(), "generic"
                        if any(kw in desc for kw in ["auth", "permission"]): cat = "authorization"
                        elif any(kw in desc for kw in ["event", "log"]): cat = "event"
                        elif any(kw in desc for kw in ["read", "write", "file", "db", "query"]): cat = "io"
                        elif any(kw in desc for kw in ["validate", "check"]): cat = "validation"
                        rules_list.append({"source_function": f.get("name"), "category": cat, "description": r})
                scanner = VulnerabilityScanner(indexer); scanner_f = []
                for f in funcs:
                    sf = f.copy(); sf["mass"] = cognitive_info.get(f.get("name"), {}).get("mass", 1.0); sf["business_score"] = 0.5; scanner_f.append(sf)
                scanner.set_data(scanner_f, rules_list); raw_vulns = scanner.run_all_scans()
                for rv in raw_vulns:
                    msg = rv.get("description") or rv.get("message")
                    vulnerabilities.append({"cwe": rv.get("cwe", "CWE-Unknown"), "severity": rv.get("severity", "LOW"), "function": rv.get("function"), "description": msg, "message": msg})
            except Exception as e: console.print(f"[yellow]Warning: security scanner failed: {e}[/yellow]")

            try:
                system_auditor = SystemicAuditor(indexer, calls_map, funcs); finder = EntrypointFinder(repo_path)
                mapped_ep = []
                for ep in finder.find_entrypoints():
                    ep_p = ep.get("file", ""); qn = short_to_qualified.get(ep_p) or next((f.get("name") for f in funcs if f.get("file") == ep_p), ep.get("name"))
                    if qn: mapped_ep.append({"name": qn, "file": ep_p})
                for sf in system_auditor.audit_all_entrypoints(mapped_ep):
                    desc = f"Global flow: {sf['path']} -> {sf['sink']} ({sf['variable']})"
                    vulnerabilities.append({"cwe": "CWE-Global", "severity": sf["severity"], "function": sf["path"].split(" -> ")[0], "description": desc, "message": desc})
            except Exception as e: console.print(f"[yellow]Warning: systemic audit failed: {e}[/yellow]")

            for v in vulnerabilities: v["safe_link"] = engine._get_safe_filename(v.get("function", "unknown"))

            # 6. Export
            console.print("Exporting enriched vault...")
            all_w, all_s_map = [], {}
            for f in funcs:
                name, f_path = f.get("name"), f.get("file"); pg = parser.parse_genome(f)
                if pg.get("warnings"): all_w.append({"name": name, "file": pg.get("file"), "warnings": pg.get("warnings")})
                sv = [v for v in vulnerabilities if str(v.get("function")).strip() == str(name).strip()]
                labels = f.get("labels", [])
                skind = next((k for k in ["Class", "Interface", "Enum", "Variable", "Method", "Function", "Module"] if k in labels), "Function")
                sd = {
                    "name": name, "language": f.get("language") or "generic", "file": f_path, "kind": skind, "signature": f.get("signature") or name, "docstring": f.get("docstring"), "params": pg.get("params", []), "returns": pg.get("returns", {}), "business_rules": pg.get("business_rules", []), 
                    "code_snippet": f.get("code_snippet") if skind != "Module" else f"[Full file context available in Files folder: {f_path}]",
                    "mass": cognitive_info.get(name, {}).get("mass", 1.0), "potential_energy": cognitive_info.get(name, {}).get("potential_energy", 0.0), "archetype": cognitive_info.get(name, {}).get("archetype", "generic"), "semantic_neighbors": semantic_neighbors.get(name, []), "callers": calls_map.get(name, {}).get("callers", []), "callees": calls_map.get(name, {}).get("callees", []), "vulnerabilities": sv, "line": f.get("line"), "line_range": [int(f.get("line", 0) or 0), int(f.get("end_line", 0) or 0)], "variable_states": f.get("variable_states", {}), "flow_paths": f.get("flow_paths", []), "members": []
                }
                all_s_map[name] = sd

            for name, sd in all_s_map.items():
                k, fp = sd.get("kind"), sd.get("file")
                if k in ["Method", "Variable", "Function"] and fp:
                    for other in file_symbols_data.get(fp, []):
                        oname = other.get("name")
                        if oname in all_s_map and all_s_map[oname].get("kind") in ["Class", "Interface", "Enum"] and oname != name:
                            if all_s_map[oname].get("line_range") and sd.get("line"):
                                start, end = all_s_map[oname]["line_range"]
                                if start <= int(sd["line"]) <= end: all_s_map[oname]["members"].append(sd); break

            for name, sd in all_s_map.items():
                if sd.get("kind") in ["Class", "Interface", "Enum"]: engine.export_symbol(sd)
                elif sd.get("kind") != "Module": engine.export_symbol(sd, subdirectory="granular")

            for fp, f_syms in file_symbols_data.items():
                lang = f_syms[0].get("language") or "generic"
                size, loc = 0, 0
                full_p = os.path.normpath(fp if os.path.isabs(fp) else os.path.join(repo_path, fp))
                if not os.path.exists(full_p):
                    fb = os.path.join(repo_path, os.path.basename(fp))
                    if os.path.exists(fb): full_p = fb
                    else:
                        fname = os.path.basename(fp)
                        for r, _, fs in os.walk(repo_path):
                            if fname in fs: full_p = os.path.join(r, fname); break
                if os.path.exists(full_p):
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as fo: loc = len(fo.readlines())
                        size = os.path.getsize(full_p)
                    except Exception: pass
                
                fvs = {}
                for s in f_syms: fvs.update(all_s_map.get(s.get("name"), {}).get("variable_states", {}))
                lsd = [{"name": s.get("name"), "kind": all_s_map.get(s.get("name"), {}).get("kind"), "signature": all_s_map.get(s.get("name"), {}).get("signature"), "docstring": s.get("docstring"), "business_rules": all_s_map.get(s.get("name"), {}).get("business_rules", []), "flow_paths": all_s_map.get(s.get("name"), {}).get("flow_paths", [])} for s in f_syms]
                engine.export_file({"file_path": fp, "language": lang, "lines_of_code": loc, "size": size, "symbols": [s.get("name") for s in f_syms], "symbols_data": lsd, "variable_states": fvs})

            for ep in mapped_ep:
                model = engine.generate_behavior_model(ep["name"], ep["file"], calls_map, funcs, all_s_map)
                engine.export_behavior(model)

            engine.export_warnings(all_w)
            engine.export_vulnerabilities(vulnerabilities)
            engine.export_hotspots({"complexity": sorted([{"name": k, "mass": v["mass"], "archetype": v["archetype"], "file": v.get("file", "unknown")} for k, v in cognitive_info.items()], key=lambda x: x["mass"], reverse=True)[:10], "attention": sorted([{"name": k, "potential_energy": v["potential_energy"], "archetype": v["archetype"], "file": v.get("file", "unknown")} for k, v in cognitive_info.items()], key=lambda x: x["potential_energy"], reverse=True)[:10]})
            ag = {}
            for k, v in cognitive_info.items(): ag.setdefault(v["archetype"], []).append({"name": k, "mass": v["mass"], "potential_energy": v["potential_energy"]})
            engine.export_archetypes(ag)
            engine.export_branch_diff(branch_diff.compare_branches(branch_diff.get_default_branch(), "HEAD"))

        console.print("[green]Obsidian Vault synchronized successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error during library sync: {e}[/red]")
        logger.exception("Library sync failed")
