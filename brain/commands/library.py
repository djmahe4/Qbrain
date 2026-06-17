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
from brain.global_registry import GlobalRegistry
from brain.parsers import php as php_parser

logger = logging.getLogger(__name__)

def sync_library(config, indexer, console):
    repo_path = config.repo_path
    vault_path = config.data.get("vault_path", os.path.join(repo_path, "obsidian_vault"))
    
    console.print(f"Syncing librarian from repository [cyan]{repo_path}[/cyan] to vault [cyan]{vault_path}[/cyan]...")
    
    engine = LibrarianEngine(repo_path, vault_path, indexer=indexer)
    
    try:
        with engine.lock():
            engine.setup_vault()
            
            # 1. Load cognitive data from graph and SQLite sidecar
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
                        mass = item.get("mass")
                        pe = item.get("potential_energy")
                        arch = item.get("archetype")
                        cognitive_info[name] = {
                            "mass": float(mass) if (mass is not None and str(mass).strip() != "") else 1.0,
                            "potential_energy": float(pe) if (pe is not None and str(pe).strip() != "") else 0.0,
                            "archetype": arch if (arch is not None and str(arch).strip() != "") else "generic"
                        }
            except Exception as e:
                console.print(f"[yellow]Warning: could not load cognitive metadata from graph: {e}[/yellow]")

            try:
                internal_beliefs = indexer.persistence.get_internal_beliefs()
                for b in internal_beliefs:
                    name = b.get("symbol")
                    if name:
                        if name not in cognitive_info:
                            cognitive_info[name] = {
                                "mass": b.get("support_mass", 1.0),
                                "potential_energy": b.get("potential_energy", 0.0),
                                "archetype": b.get("winner", "generic")
                            }
                        else:
                            cognitive_info[name]["mass"] = b.get("support_mass", cognitive_info[name]["mass"])
                            cognitive_info[name]["potential_energy"] = b.get("potential_energy", cognitive_info[name]["potential_energy"])
                            cognitive_info[name]["archetype"] = b.get("winner", cognitive_info[name]["archetype"])
            except Exception as e:
                console.print(f"[yellow]Warning: could not merge SQLite beliefs: {e}[/yellow]")

            _pe_mostly_zero = sum(1 for v in cognitive_info.values() if v.get("potential_energy", 0.0) == 0.0) / max(len(cognitive_info), 1) > 0.8 if cognitive_info else True
            
            # 2. Query CALLS relationships
            console.print("Mapping function entanglements...")
            calls_map = {}
            try:
                calls_res = indexer.query_graph("MATCH (a)-[:CALLS]->(b) RETURN a.name AS caller, b.name AS callee")
                for item in calls_res:
                    caller, callee = item.get("caller"), item.get("callee")
                    if caller and callee:
                        calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
                        calls_map.setdefault(callee, {}).setdefault("callers", []).append(caller)
            except Exception as e:
                console.print(f"[yellow]Warning: could not map function calls from graph: {e}[/yellow]")

            try:
                for ent in indexer.persistence.get_internal_entanglements():
                    caller, callee = ent.get("source"), ent.get("target")
                    if caller and callee:
                        if callee not in calls_map.get(caller, {}).get("callees", []):
                            calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
            except Exception as e:
                console.print(f"[yellow]Warning: could not map function entanglements: {e}[/yellow]")
            # 2.5 Environmental Pre-Scan (Bootstrap & Global Constants)
            console.print("Executing environmental pre-scan (global constants)...")
            registry = GlobalRegistry()
            setup_patterns = [
                r"config.*\.php$", r"bootstrap.*\.php$", r"common\.php$", 
                r"\.env$", r"settings\.php$", r"init\.php$"
            ]
            
            setup_files = []
            for root, _, files in os.walk(repo_path):
                if any(x in root for x in ["obsidian_vault", ".git", "node_modules", "vendor"]):
                    continue
                for file in files:
                    if any(re.match(pattern, file, re.IGNORECASE) for pattern in setup_patterns):
                        setup_files.append(os.path.join(root, file))
            
            for setup_file in setup_files:
                try:
                    with open(setup_file, "r", errors="ignore") as f:
                        content = f.read()
                    
                    rel_path = os.path.relpath(setup_file, repo_path)
                    
                    if setup_file.lower().endswith(".php"):
                        found_globals = php_parser.extract_globals(content)
                        for name, value in found_globals.items():
                            registry.register_constant(name, value, origin=rel_path)
                    elif setup_file.lower().endswith(".env"):
                        for line in content.splitlines():
                            line = line.strip()
                            if not line or line.startswith("#"): continue
                            if "=" in line:
                                key, val = line.split("=", 1)
                                registry.register_env(key.strip(), val.strip().strip("'\""))
                except Exception as e:
                    logger.warning(f"Failed to scan bootstrap file {setup_file}: {e}")

            # 3. Retrieve functions and analyze dataflow
            parser = DocstringParser(indexer)
            df_engine = DataFlowEngine()
            
            all_symbols_res = indexer.query_graph("MATCH (n) WHERE n:Function OR n:Method OR n:Module OR n:Class OR n:Interface OR n:Enum RETURN n.name AS name, labels(n) AS labels, n.file_path AS file, n.file AS file_alt")
            
            funcs = parser.get_functions_with_docstrings()
            existing_names = {f["name"] for f in funcs}
            _EXCLUDED_EXTS = {".md", ".json", ".txt", ".yaml", ".yml", ".lock", ".log", ".toml"}
            for item in all_symbols_res:
                s_name = item.get("name")
                f_path = (item.get("file") or item.get("file_alt") or "").lower()
                if s_name and s_name not in existing_names:
                    if any(f_path.endswith(ext) for ext in _EXCLUDED_EXTS): continue
                    funcs.append({"name": s_name, "file": item.get("file") or item.get("file_alt"), "labels": item.get("labels", []), "docstring": "", "language": detect_language(f_path)})

            short_to_qualified: dict = {}
            for f in funcs:
                fname = f.get("name", "")
                short_to_qualified[fname.split("/")[-1].split(".")[-1]] = fname
                short_to_qualified[fname] = fname
                if f.get("file"): short_to_qualified[f.get("file")] = fname

            for f in funcs:
                name, f_path, labels = f.get("name"), f.get("file"), f.get("labels", [])
                lang = f.get("language") or detect_language(f_path or "")
                f["language"] = lang
                if lang in {"yaml", "markdown", "toml", "json", "generic"}:
                    f["code_snippet"], f["variable_states"], f["flow_paths"] = "", {}, []
                    continue
                
                if "Module" in labels:
                    f["code_snippet"] = ""
                    full_path = os.path.join(config.repo_path, f_path) if f_path else ""
                    if full_path and os.path.exists(full_path):
                         try:
                             with open(full_path, "r", encoding="utf-8", errors="ignore") as file_obj: f["code_snippet"] = file_obj.read()
                         except Exception: pass
                else:
                    try: f["code_snippet"] = indexer.get_code_snippet(name).get("code") or ""
                    except Exception: f["code_snippet"] = ""
                
                df_res = df_engine.analyze_snippet(f["code_snippet"], lang, registry=registry)
                f["variable_states"], f["flow_paths"], f["dataflow"] = df_res.get("variable_states", {}), df_res.get("flow_paths", []), df_res.get("raw_atoms", [])

                for sync_call in df_res.get("synthesized_calls", []):
                    verb, hint = sync_call.get("verb"), sync_call.get("resolved")
                    if hint:
                        target_node = None
                        clean_hint = hint.replace("{", "").replace("}", "").strip("'\" ")
                        for potential in funcs:
                            if clean_hint in potential.get("name", ""):
                                target_node = potential.get("name")
                                break
                        final_target = target_node or f"[{verb}] {hint}"
                        condition = ", ".join(sync_call.get("constraints", [])) if sync_call.get("constraints") else None

                        if (final_target, condition) not in calls_map.get(name, {}).get("callees_detailed", []):
                            calls_map.setdefault(name, {}).setdefault("callees_detailed", []).append((final_target, condition))
                            calls_map.setdefault(name, {}).setdefault("callees", []).append(final_target)
                        if name not in calls_map.get(final_target, {}).get("callers", []):
                            calls_map.setdefault(final_target, {}).setdefault("callers", []).append(name)

            # 4. Semantic neighbors & potential energy
            semantic_neighbors = {}
            _func_embeddings: dict = {}
            try:
                embedder = Embedder()
                genomes = [DocstringParser.build_genome(f) for f in funcs]
                if genomes:
                    embeddings = embedder.embed(genomes)
                    for i, f in enumerate(funcs):
                        fname = f.get("name")
                        _func_embeddings[fname] = embeddings[i]
                        similarities = []
                        for j, f_other in enumerate(funcs):
                            if i == j: continue
                            similarities.append((f_other.get("name"), Embedder.cosine_similarity(embeddings[i], embeddings[j])))
                        similarities.sort(key=lambda x: x[1], reverse=True)
                        semantic_neighbors[fname] = similarities[:3]
            except Exception as e:
                console.print(f"[yellow]Warning: could not calculate semantic neighbors: {e}[/yellow]")

            if _pe_mostly_zero and _func_embeddings:
                console.print("[dim]Computing potential energy inline...[/dim]")
                try:
                    scorer = QuantumScorer(config, indexer)
                    nodes_for_pe = []
                    for f in funcs:
                        fname = f.get("name")
                        emb = _func_embeddings.get(fname)
                        if emb is None: continue
                        nodes_for_pe.append(FunctionNode(name=fname, embedding=emb, complexity=float(f.get("complexity", 1.0) or 1.0), side_effects=float(f.get("sideEffects", 0.0) or 0.0), is_exported=bool(f.get("isExported", False)), file=f.get("file", ""), line=int(f.get("line", 0) or 0)))
                    scorer.run_simulation(nodes_for_pe, iterations=30)
                    for node in nodes_for_pe:
                        if node.name in cognitive_info:
                            cognitive_info[node.name]["potential_energy"], cognitive_info[node.name]["archetype"] = node.potential_energy, node.quantum_state
                        else:
                            cognitive_info[node.name] = {"mass": node.mass, "potential_energy": node.potential_energy, "archetype": node.quantum_state}
                    scorer.write_physics_to_graph(nodes_for_pe)
                except Exception as e:
                    console.print(f"[yellow]Warning: inline PE computation failed: {e}[/yellow]")

            # 5. Vulnerability Scan
            console.print("Running security vulnerability scans...")
            vulnerabilities = []
            rules_list = []
            for f in funcs:
                parsed_genome = parser.parse_genome(f)
                for r in parsed_genome.get("business_rules", []):
                    desc, category = r.lower(), "generic"
                    if any(kw in desc for kw in ["auth", "permission"]): category = "authorization"
                    elif any(kw in desc for kw in ["event", "log"]): category = "event"
                    elif any(kw in desc for kw in ["read", "write", "file", "db", "query"]): category = "io"
                    elif any(kw in desc for kw in ["validate", "check"]): category = "validation"
                    rules_list.append({"source_function": f.get("name"), "category": category, "description": r})

            try:
                scanner = VulnerabilityScanner(indexer)
                scanner_funcs = []
                for f in funcs:
                    sf = f.copy()
                    sf["mass"] = cognitive_info.get(f.get("name"), {}).get("mass", 1.0)
                    sf["business_score"] = 0.5
                    scanner_funcs.append(sf)
                scanner.set_data(scanner_funcs, rules_list)
                for rv in scanner.run_all_scans():
                    v_msg = rv.get("description") or rv.get("message")
                    vulnerabilities.append({"cwe": rv.get("cwe", "CWE-Unknown"), "severity": rv.get("severity", "LOW"), "function": rv.get("function"), "description": v_msg, "message": v_msg})
            except Exception as e:
                console.print(f"[yellow]Warning: could not run security scanner: {e}[/yellow]")

            entrypoints = []
            try:
                system_auditor = SystemicAuditor(indexer, calls_map, funcs)
                finder = EntrypointFinder(repo_path)
                entrypoints = finder.find_entrypoints()
                mapped_entrypoints = []
                for ep in entrypoints:
                    ep_path = ep.get("file", "")
                    q_name = short_to_qualified.get(ep_path) or next((f.get("name") for f in funcs if f.get("file") == ep_path), ep.get("name"))
                    if q_name: mapped_entrypoints.append({"name": q_name, "file": ep_path})
                for sf in system_auditor.audit_all_entrypoints(mapped_entrypoints):
                    v_desc = f"Global flow: {sf['path']} -> {sf['sink']} ({sf['variable']})"
                    vulnerabilities.append({"cwe": "CWE-Global", "severity": sf["severity"], "function": sf["path"].split(" -> ")[0], "description": v_desc, "message": v_desc})
            except Exception as e:
                console.print(f"[yellow]Warning: systemic audit failed: {e}[/yellow]")

            for v in vulnerabilities: v["safe_link"] = engine._get_safe_filename(v.get("function", "unknown"))

            # 6. Export
            console.print("Exporting enriched vault...")
            all_warnings, file_symbols_data = [], {}

            for f in funcs:
                name, f_path = f.get("name"), f.get("file")
                parsed_genome = parser.parse_genome(f)
                if parsed_genome.get("warnings"): all_warnings.append({"name": name, "file": parsed_genome.get("file"), "warnings": parsed_genome.get("warnings")})
                
                symbol_vulns = [v for v in vulnerabilities if str(v.get("function")).strip() == str(name).strip()]
                start_l, end_l = f.get("line"), f.get("end_line")
                symbol_kind = next((k for k in ["Class", "Interface", "Enum", "Variable", "Method", "Function", "Module"] if k in f.get("labels", [])), "Function")

                symbol_data = {
                    "name": name, "language": f.get("language") or "generic", "file": f_path, "kind": symbol_kind,
                    "signature": f.get("signature") or name, "docstring": f.get("docstring"),
                    "params": parsed_genome.get("params", []), "returns": parsed_genome.get("returns", {}),
                    "business_rules": parsed_genome.get("business_rules", []), "code_snippet": f.get("code_snippet"),
                    "mass": cognitive_info.get(name, {}).get("mass", 1.0), "potential_energy": cognitive_info.get(name, {}).get("potential_energy", 0.0),
                    "archetype": cognitive_info.get(name, {}).get("archetype", "generic"), "semantic_neighbors": semantic_neighbors.get(name, []),
                    "callers": calls_map.get(name, {}).get("callers", []), "callees": calls_map.get(name, {}).get("callees", []),
                    "vulnerabilities": symbol_vulns, "line": int(start_l) if start_l is not None else None,
                    "line_range": [int(start_l), int(end_l)] if (start_l is not None and end_l is not None) else None,
                    "variable_states": f.get("variable_states", {}), "flow_paths": f.get("flow_paths", [])
                }
                
                if symbol_kind in ["Class", "Interface", "Enum"]: engine.export_symbol(symbol_data)
                if f_path: file_symbols_data.setdefault(f_path, []).append(symbol_data)

            files_map = {}
            for f in funcs:
                if f.get("file"): files_map.setdefault(f.get("file"), []).append(f)
            
            for f_path, file_funcs in files_map.items():
                size_bytes, lines_of_code = 0, 0
                full_path = os.path.normpath(f_path if os.path.isabs(f_path) else os.path.join(repo_path, f_path))
                if not os.path.exists(full_path):
                    for root, _, files in os.walk(repo_path):
                        if os.path.basename(f_path) in files:
                            full_path = os.path.join(root, os.path.basename(f_path))
                            break
                if os.path.exists(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as file_obj: lines_of_code = len(file_obj.readlines())
                        size_bytes = os.path.getsize(full_path)
                    except Exception: pass
                
                file_var_states = {}
                for fn in file_funcs: file_var_states.update(fn.get("variable_states", {}))
                engine.export_file({
                    "file_path": f_path, "language": file_funcs[0].get("language") or "generic", "lines_of_code": lines_of_code, "size_bytes": size_bytes,
                    "symbols": [fn.get("name") for fn in file_funcs if fn.get("name")], "symbols_data": file_symbols_data.get(f_path, []), "variable_states": file_var_states
                })

            engine.export_warnings(all_warnings)
            engine.export_vulnerabilities(vulnerabilities)
            engine.export_hotspots({"complexity": sorted([{"name": k, "mass": v["mass"], "archetype": v["archetype"]} for k, v in cognitive_info.items()], key=lambda x: x["mass"], reverse=True)[:10], "attention": sorted([{"name": k, "potential_energy": v["potential_energy"], "archetype": v["archetype"]} for k, v in cognitive_info.items()], key=lambda x: x["potential_energy"], reverse=True)[:10]})
            
            archetype_groups = {}
            for k, v in cognitive_info.items():
                archetype_groups.setdefault(v["archetype"], []).append({"name": k, "mass": v["mass"], "potential_energy": v["potential_energy"], "variable_states": next((f.get("variable_states", {}) for f in funcs if f.get("name") == k), {}), "flow_paths": next((f.get("flow_paths", []) for f in funcs if f.get("name") == k), []), "confidence": 0.95})
            
            engine.export_archetypes(archetype_groups)
            for arch, symbols in archetype_groups.items(): engine.export_narrative(arch, symbols)

            sym_meta = {}
            for f in funcs:
                name = f.get("name")
                cog = cognitive_info.get(name, {})
                sym_meta[name] = {"params": f.get("params", []), "returns": f.get("returns", {}), "docstring": f.get("docstring") or "", "potential_energy": cog.get("potential_energy", 0.0), "archetype": cog.get("archetype", "generic"), "variable_states": f.get("variable_states", {}), "flow_paths": f.get("flow_paths", [])}

            # Consolidate entrypoints by directory to reduce redundancy (e.g. low/med/high variants)
            grouped_eps = {}
            for ep in entrypoints:
                path = ep.get("file", "")
                group_key = os.path.dirname(path) if path else "root"
                if group_key not in grouped_eps:
                    grouped_eps[group_key] = ep
                else:
                    # Generic preference: prefer 'index' or the shortest filename as the representative
                    curr_name = os.path.basename(grouped_eps[group_key].get("file", "")).lower()
                    new_name = os.path.basename(path).lower()
                    if "index" in new_name and "index" not in curr_name:
                        grouped_eps[group_key] = ep
                    elif len(new_name) < len(curr_name) and "index" not in curr_name:
                        grouped_eps[group_key] = ep

            for group_path, ep in grouped_eps.items():
                ep_path = ep.get("file", "")
                ep_func = short_to_qualified.get(ep_path) or next((f.get("name") for f in funcs if f.get("file") == ep_path), ep.get("name", "main"))
                
                model = engine.generate_behavior_model(ep_func, ep_path, calls_map, funcs, sym_meta, config.data.get("behavior_max_depth", 10), config.data.get("behavior_max_states", 50))
                
                # If this is a representative of a directory group, name the behavior after the directory
                if group_path != "root" and "index" in os.path.basename(ep_path).lower():
                    model["name"] = group_path.replace("/", "_")
                
                engine.export_behavior(model)

            try:
                diff_tool = BranchDiff(config, Embedder())
                engine.export_branch_diff(diff_tool.compare_branches("HEAD", config.data.get("branch_diff", {}).get("base_branch") or diff_tool.get_default_branch()))
            except Exception: pass

            console.print("[green]Obsidian Vault synchronized successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error during librarian sync:[/red] {e}")
        logger.exception("Library sync failed")