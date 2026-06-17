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
    
    engine = LibrarianEngine(repo_path, vault_path)
    
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

            _zero_count = sum(1 for v in cognitive_info.values() if v.get("potential_energy", 0.0) == 0.0)
            _pe_mostly_zero = (_zero_count / max(len(cognitive_info), 1)) > 0.8 if cognitive_info else True
            
            # 2. Query CALLS relationships
            console.print("Mapping function entanglements...")
            calls_map = {}
            try:
                calls_res = indexer.query_graph("MATCH (a)-[:CALLS]->(b) RETURN a.name AS caller, b.name AS callee")
                for item in calls_res:
                    caller = item.get("caller")
                    callee = item.get("callee")
                    if caller and callee:
                        calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
                        calls_map.setdefault(callee, {}).setdefault("callers", []).append(caller)
            except Exception as e:
                console.print(f"[yellow]Warning: could not map function calls from graph: {e}[/yellow]")

            try:
                internal_ent = indexer.persistence.get_internal_entanglements()
                for ent in internal_ent:
                    caller = ent.get("source")
                    callee = ent.get("target")
                    if caller and callee:
                        if callee not in calls_map.get(caller, {}).get("callees", []):
                            calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
                        if caller not in calls_map.get(callee, {}).get("callers", []):
                            calls_map.setdefault(callee, {}).setdefault("callers", []).append(caller)
            except Exception as e:
                console.print(f"[yellow]Warning: could not merge SQLite entanglements: {e}[/yellow]")

            # 3. Retrieve functions and analyze dataflow
            parser = DocstringParser(indexer)
            df_engine = DataFlowEngine()
            
            # Retrieve all symbols (including those without docstrings) for comprehensive analysis
            all_symbols_res = indexer.query_graph("MATCH (n) WHERE n:Function OR n:Method OR n:Module OR n:Class OR n:Interface OR n:Enum RETURN n.name AS name, labels(n) AS labels, n.file_path AS file, n.file AS file_alt")
            
            funcs = parser.get_functions_with_docstrings()
            existing_names = {f["name"] for f in funcs}
            _EXCLUDED_EXTS = {".md", ".json", ".txt", ".yaml", ".yml", ".lock", ".log", ".toml"}
            for item in all_symbols_res:
                s_name = item.get("name")
                f_path = (item.get("file") or item.get("file_alt") or "").lower()
                if s_name and s_name not in existing_names:
                    if any(f_path.endswith(ext) for ext in _EXCLUDED_EXTS):
                        continue
                    funcs.append({
                        "name": s_name,
                        "file": item.get("file") or item.get("file_alt"),
                        "labels": item.get("labels", []),
                        "docstring": "",
                        "language": detect_language(f_path)
                    })

            # Build name resolution maps
            short_to_qualified: dict = {}
            for f in funcs:
                fname = f.get("name", "")
                short_to_qualified[fname.split("/")[-1].split(".")[-1]] = fname
                short_to_qualified[fname] = fname
                f_path = f.get("file", "")
                if f_path:
                    short_to_qualified[f_path] = fname

            _SKIP_CODE_ANALYSIS = {"yaml", "markdown", "toml", "json", "generic"}
            for f in funcs:
                name = f.get("name")
                f_path = f.get("file")
                labels = f.get("labels", [])
                
                lang = f.get("language") or detect_language(f_path or "")
                f["language"] = lang
                
                if lang in _SKIP_CODE_ANALYSIS:
                    f["code_snippet"] = ""
                    f["variable_states"] = {}
                    f["flow_paths"] = []
                    continue
                
                if "Module" in labels:
                    f["code_snippet"] = ""
                    full_path = os.path.join(config.repo_path, f_path) if f_path else ""
                    if full_path and os.path.exists(full_path):
                         try:
                             with open(full_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                                 f["code_snippet"] = file_obj.read()
                         except Exception: pass
                else:
                    try:
                        snippet_res = indexer.get_code_snippet(name)
                        f["code_snippet"] = snippet_res.get("code") or ""
                    except Exception:
                        f["code_snippet"] = ""
                
                df_res = df_engine.analyze_snippet(f["code_snippet"], lang)
                f["variable_states"] = df_res.get("variable_states", {})
                f["flow_paths"] = df_res.get("flow_paths", [])
                f["dataflow"] = df_res.get("raw_atoms", [])  # Persist raw atoms for behavior mapping

                # Merge Synthesized Calls
                for sync_call in df_res.get("synthesized_calls", []):
                    verb = sync_call.get("verb")
                    hint = sync_call.get("resolved_hint")
                    if hint:
                        target_node = None
                        clean_hint = hint.replace("{", "").replace("}", "").strip("'\" ")
                        for potential in funcs:
                            if clean_hint in potential.get("name", ""):
                                target_node = potential.get("name")
                                break
                        final_target = target_node or f"[{verb}] {hint}"
                        
                        # Capture constraints for transition labels
                        constraints = sync_call.get("constraints", [])
                        condition = ", ".join(constraints) if constraints else None

                        if (final_target, condition) not in calls_map.get(name, {}).get("callees_detailed", []):
                            calls_map.setdefault(name, {}).setdefault("callees_detailed", []).append((final_target, condition))
                            calls_map.setdefault(name, {}).setdefault("callees", []).append(final_target)
                        
                        if name not in calls_map.get(final_target, {}).get("callers", []):
                            calls_map.setdefault(final_target, {}).setdefault("callers", []).append(name)
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
                            sim = Embedder.cosine_similarity(embeddings[i], embeddings[j])
                            similarities.append((f_other.get("name"), sim))
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
                        node = FunctionNode(
                            name=fname, embedding=emb,
                            complexity=float(f.get("complexity", 1.0) or 1.0),
                            side_effects=float(f.get("sideEffects", 0.0) or 0.0),
                            is_exported=bool(f.get("isExported", False)),
                            file=f.get("file", ""),
                            line=int(f.get("line", 0) or 0),
                        )
                        nodes_for_pe.append(node)
                    scorer.run_simulation(nodes_for_pe, iterations=30)
                    for node in nodes_for_pe:
                        if node.name in cognitive_info:
                            cognitive_info[node.name]["potential_energy"] = node.potential_energy
                            cognitive_info[node.name]["archetype"] = node.quantum_state
                        else:
                            cognitive_info[node.name] = {
                                "mass": node.mass, "potential_energy": node.potential_energy,
                                "archetype": node.quantum_state,
                            }
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
                    desc = r.lower()
                    category = "generic"
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
                raw_vulns = scanner.run_all_scans()
                for rv in raw_vulns:
                    v_msg = rv.get("description") or rv.get("message")
                    vulnerabilities.append({
                        "cwe": rv.get("cwe", "CWE-Unknown"),
                        "severity": rv.get("severity", "LOW"),
                        "function": rv.get("function"),
                        "description": v_msg,
                        "message": v_msg
                    })
            except Exception as e:
                console.print(f"[yellow]Warning: could not run security scanner: {e}[/yellow]")

            # Systemic Audit
            entrypoints = []
            try:
                system_auditor = SystemicAuditor(indexer, calls_map, funcs)
                finder = EntrypointFinder(repo_path)
                entrypoints = finder.find_entrypoints()
                
                mapped_entrypoints = []
                for ep in entrypoints:
                    ep_path = ep.get("file", "")
                    q_name = short_to_qualified.get(ep_path) or next((f.get("name") for f in funcs if f.get("file") == ep_path), ep.get("name"))
                    if q_name:
                        mapped_entrypoints.append({"name": q_name, "file": ep_path})
                
                systemic_findings = system_auditor.audit_all_entrypoints(mapped_entrypoints)
                for sf in systemic_findings:
                    v_desc = f"Global flow: {sf['path']} -> {sf['sink']} ({sf['variable']})"
                    vulnerabilities.append({
                        "cwe": "CWE-Global", "severity": sf["severity"],
                        "function": sf["path"].split(" -> ")[0],
                        "description": v_desc, "message": v_desc
                    })
            except Exception as e:
                console.print(f"[yellow]Warning: systemic audit failed: {e}[/yellow]")

            # Standardize for Obsidian links
            for v in vulnerabilities:
                v["safe_link"] = engine._get_safe_filename(v.get("function", "unknown"))

            # 6. Export
            console.print("Exporting enriched vault...")
            all_warnings = []
            file_symbols_data = {}  # Collect data for holistic file export

            for f in funcs:
                name = f.get("name")
                f_path = f.get("file")
                parsed_genome = parser.parse_genome(f)
                if parsed_genome.get("warnings"):
                    all_warnings.append({"name": name, "file": parsed_genome.get("file"), "warnings": parsed_genome.get("warnings")})
                
                symbol_vulns = [v for v in vulnerabilities if str(v.get("function")).strip() == str(name).strip()]
                start_l = f.get("line")
                end_l = f.get("end_line")
                line_range = [int(start_l), int(end_l)] if (start_l is not None and end_l is not None) else None

                labels = f.get("labels", [])
                _kind_priority = ["Class", "Interface", "Enum", "Variable", "Method", "Function", "Module"]
                symbol_kind = next((k for k in _kind_priority if k in labels), "Function")

                symbol_data = {
                    "name": name, "language": f.get("language") or "generic", "file": f_path,
                    "kind": symbol_kind,
                    "signature": f.get("signature") or name, "docstring": f.get("docstring"),
                    "params": parsed_genome.get("params", []), "returns": parsed_genome.get("returns", {}),
                    "business_rules": parsed_genome.get("business_rules", []), "code_snippet": f.get("code_snippet"),
                    "mass": cognitive_info.get(name, {}).get("mass", 1.0),
                    "potential_energy": cognitive_info.get(name, {}).get("potential_energy", 0.0),
                    "archetype": cognitive_info.get(name, {}).get("archetype", "generic"),
                    "semantic_neighbors": semantic_neighbors.get(name, []),
                    "callers": calls_map.get(name, {}).get("callers", []), "callees": calls_map.get(name, {}).get("callees", []),
                    "vulnerabilities": symbol_vulns, "line": int(start_l) if start_l is not None else None,
                    "line_range": line_range, "variable_states": f.get("variable_states", {}), "flow_paths": f.get("flow_paths", [])
                }
                
                # Noise reduction: only export Class-level symbols individually
                if symbol_kind in ["Class", "Interface", "Enum"]:
                    engine.export_symbol(symbol_data)
                
                # Store for holistic file documentation
                if f_path:
                    file_symbols_data.setdefault(f_path, []).append(symbol_data)

            # File mappings
            files_map = {}
            for f in funcs:
                f_path = f.get("file")
                if f_path: files_map.setdefault(f_path, []).append(f)
            
            for f_path, file_funcs in files_map.items():
                lang = file_funcs[0].get("language") or "generic"
                symbols_list = [fn.get("name") for fn in file_funcs if fn.get("name")]
                size_bytes = 0
                lines_of_code = 0
                full_path = f_path if os.path.isabs(f_path) else os.path.join(repo_path, f_path)
                full_path = os.path.normpath(full_path)
                if not os.path.exists(full_path):
                    fallback_path = os.path.join(repo_path, os.path.basename(f_path))
                    if os.path.exists(fallback_path):
                        full_path = fallback_path
                    else:
                        # Recursively search for the filename under repo_path
                        fname = os.path.basename(f_path)
                        for root, _, files in os.walk(repo_path):
                            if fname in files:
                                full_path = os.path.join(root, fname)
                                break
                if os.path.exists(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                            lines_of_code = len(file_obj.readlines())
                        size_bytes = os.path.getsize(full_path)
                    except Exception: pass
                file_var_states = {}
                for fn in file_funcs: file_var_states.update(fn.get("variable_states", {}))
                engine.export_file({
                    "file_path": f_path, 
                    "language": lang, 
                    "lines_of_code": lines_of_code, 
                    "size_bytes": size_bytes, 
                    "symbols": symbols_list, 
                    "symbols_data": file_symbols_data.get(f_path, []),  # Holistic awareness
                    "variable_states": file_var_states
                })


            # Reports
            engine.export_warnings(all_warnings)
            engine.export_vulnerabilities(vulnerabilities)
            
            # Hotspots & Archetypes
            complexity_hotspots = sorted([{"name": k, "mass": v["mass"], "archetype": v["archetype"]} for k, v in cognitive_info.items()], key=lambda x: x["mass"], reverse=True)[:10]
            attention_hotspots = sorted([{"name": k, "potential_energy": v["potential_energy"], "archetype": v["archetype"]} for k, v in cognitive_info.items()], key=lambda x: x["potential_energy"], reverse=True)[:10]
            engine.export_hotspots({"complexity": complexity_hotspots, "attention": attention_hotspots})
            
            archetype_groups = {}
            for k, v in cognitive_info.items():
                arch = v["archetype"]
                symbol_brief = {"name": k, "mass": v["mass"], "potential_energy": v["potential_energy"], "variable_states": next((f.get("variable_states", {}) for f in funcs if f.get("name") == k), {}), "flow_paths": next((f.get("flow_paths", []) for f in funcs if f.get("name") == k), []), "confidence": 0.95}
                archetype_groups.setdefault(arch, []).append(symbol_brief)
            
            engine.export_archetypes(archetype_groups)
            for arch, symbols in archetype_groups.items(): engine.export_narrative(arch, symbols)

            # Behaviors
            if not entrypoints:
                try:
                    finder = EntrypointFinder(repo_path)
                    entrypoints = finder.find_entrypoints()
                except Exception as e:
                    console.print(f"[yellow]Warning: entrypoint detection failed: {e}[/yellow]")
            if not entrypoints:
                entrypoints = []

            sym_meta = {}
            for f in funcs:
                name = f.get("name")
                cog = cognitive_info.get(name, {})
                sym_meta[name] = {"params": f.get("params", []), "returns": f.get("returns", {}), "docstring": f.get("docstring") or "", "potential_energy": cog.get("potential_energy", 0.0), "archetype": cog.get("archetype", "generic"), "variable_states": f.get("variable_states", {}), "flow_paths": f.get("flow_paths", [])}

            max_depth = config.data.get("behavior_max_depth", 10)
            max_states = config.data.get("behavior_max_states", 50)
            for ep in entrypoints:
                ep_short = ep.get("name", "main")
                ep_path = ep.get("file", "")
                ep_func = short_to_qualified.get(ep_path) or next((f.get("name") for f in funcs if f.get("file") == ep_path), ep_short)
                behavior_data = engine.generate_behavior_model(ep_func, ep_path, calls_map, funcs, sym_meta, max_depth, max_states)
                engine.export_behavior(behavior_data)

            # Branch Diff
            try:
                embedder = Embedder()
                diff_tool = BranchDiff(config, embedder)
                base_branch = config.data.get("branch_diff", {}).get("base_branch") or diff_tool.get_default_branch()
                diff_summary = diff_tool.compare_branches("HEAD", base_branch)
                engine.export_branch_diff(diff_summary)
            except Exception: pass

            console.print("[green]Obsidian Vault synchronized successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error during librarian sync:[/red] {e}")
        import traceback
        logger.error(traceback.format_exc())
