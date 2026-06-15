import os
import typer
import re
from brain.librarian import LibrarianEngine
from brain.docstring_parser import DocstringParser
from brain.vuln_scanner import VulnerabilityScanner
from brain.entrypoint_finder import EntrypointFinder
from brain.branch_diff import BranchDiff
from brain.embedder import Embedder
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.dataflow_engine import DataFlowEngine
from brain.language_parser import detect_language

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
            
            # A. Load from graph first
            try:
                cog_res = indexer.query_graph(
                    "MATCH (f) WHERE f:Function OR f:Method OR f:Module "
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

            # B. Merge from SQLite (Truth for writes)
            try:
                internal_beliefs = indexer.persistence.get_internal_beliefs()
                for b in internal_beliefs:
                    name = b.get("symbol")
                    if name:
                        # Prioritize SQLite values for PE and Mass as they are computed by qbrain
                        if name not in cognitive_info:
                            cognitive_info[name] = {
                                "mass": b.get("support_mass", 1.0),
                                "potential_energy": b.get("potential_energy", 0.0),
                                "archetype": b.get("winner", "generic")
                            }
                        else:
                            # Update existing entries with fresh SQLite data
                            cognitive_info[name]["mass"] = b.get("support_mass", cognitive_info[name]["mass"])
                            cognitive_info[name]["potential_energy"] = b.get("potential_energy", cognitive_info[name]["potential_energy"])
                            cognitive_info[name]["archetype"] = b.get("winner", cognitive_info[name]["archetype"])
            except Exception as e:
                console.print(f"[yellow]Warning: could not merge SQLite beliefs: {e}[/yellow]")

            # BUG-FIX-1: If all PE values are 0 (scorer not yet run), compute physics inline
            _pe_all_zero = all(v.get("potential_energy", 0.0) == 0.0 for v in cognitive_info.values()) if cognitive_info else True
            
            # 2. Query CALLS relationships to build caller/callee entanglements
            console.print("Mapping function entanglements...")
            calls_map = {}
            try:
                # Match all CALLS (Function, Method, Module) to capture top-level script behavior
                calls_res = indexer.query_graph("MATCH (a)-[:CALLS]->(b) RETURN a.name AS caller, b.name AS callee")
                for item in calls_res:
                    caller = item.get("caller")
                    callee = item.get("callee")
                    if caller and callee:
                        calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
                        calls_map.setdefault(callee, {}).setdefault("callers", []).append(caller)
            except Exception as e:
                console.print(f"[yellow]Warning: could not map function calls from graph: {e}[/yellow]")

            # B. Merge from SQLite (internal discoveries)
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
            funcs = parser.get_functions_with_docstrings()
            
            # Retrieve code snippets and analyze variables/dataflow for all symbols
            for f in funcs:
                name = f.get("name")
                f_path = f.get("file")
                labels = f.get("labels", [])
                
                # Ensure language is detected if missing
                if not f.get("language"):
                    f["language"] = detect_language(f_path)
                
                if "Module" in labels:
                    f["code_snippet"] = ""
                    # Modules are scripts, their code is in the file itself
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
                
                # Dataflow Analysis
                df_res = df_engine.analyze_snippet(f["code_snippet"], f["language"])
                f["variable_states"] = df_res.get("variable_states", {})
                f["flow_paths"] = df_res.get("flow_paths", [])

            # 4. Generate rules/genome and compute semantic neighbors
            console.print("Computing semantic similarity neighbors...")
            semantic_neighbors = {}
            _func_embeddings: dict = {}  # name -> np.ndarray, reused for PE computation
            try:
                embedder = Embedder()
                genomes = [DocstringParser.build_genome(f) for f in funcs]
                if genomes:
                    embeddings = embedder.embed(genomes)
                    for i, f in enumerate(funcs):
                        name = f.get("name")
                        _func_embeddings[name] = embeddings[i]
                        similarities = []
                        for j, f_other in enumerate(funcs):
                            if i == j:
                                continue
                            sim = Embedder.cosine_similarity(embeddings[i], embeddings[j])
                            similarities.append((f_other.get("name"), sim))
                        similarities.sort(key=lambda x: x[1], reverse=True)
                        semantic_neighbors[name] = similarities[:3]
            except Exception as e:
                console.print(f"[yellow]Warning: could not calculate semantic neighbors: {e}[/yellow]")

            # 4b. BUG-FIX-1: Compute potential_energy inline if graph has all-zero PE values.
            if _pe_all_zero and _func_embeddings:
                console.print("[dim]Computing potential energy inline (graph has no cached values)...[/dim]")
                try:
                    scorer = QuantumScorer(config, indexer)
                    nodes_for_pe = []
                    for f in funcs:
                        fname = f.get("name")
                        emb = _func_embeddings.get(fname)
                        if emb is None:
                            continue
                        node = FunctionNode(
                            name=fname,
                            embedding=emb,
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
                        else:
                            cognitive_info[node.name] = {
                                "mass": node.mass,
                                "potential_energy": node.potential_energy,
                                "archetype": "generic",
                            }
                    # Persist so subsequent syncs load from graph correctly
                    scorer.write_physics_to_graph(nodes_for_pe)
                except Exception as e:
                    console.print(f"[yellow]Warning: inline PE computation failed: {e}[/yellow]")

            # 5. Extract rules dynamically for security scanner
            rules_list = []
            for f in funcs:
                parsed_genome = parser.parse_genome(f)
                for r in parsed_genome.get("business_rules", []):
                    category = "generic"
                    desc = r.lower()
                    if any(kw in desc for kw in ["auth", "permission", "requires", "allow", "role", "owner"]):
                        category = "authorization"
                    elif any(kw in desc for kw in ["event", "log", "emit"]):
                        category = "event"
                    elif any(kw in desc for kw in ["read", "write", "file", "db", "query", "io"]):
                        category = "io"
                    elif any(kw in desc for kw in ["validate", "check", "ensure", "assert"]):
                        category = "validation"
                    
                    rules_list.append({
                        "source_function": f.get("name"),
                        "category": category,
                        "description": r
                    })

            # 6. Run security vulnerability scans
            console.print("Running vulnerability scans...")
            vulnerabilities = []
            try:
                scanner = VulnerabilityScanner(indexer)
                scanner_funcs = []
                for f in funcs:
                    sf = f.copy()
                    sf["mass"] = cognitive_info.get(f.get("name"), {}).get("mass", 1.0)
                    sf["business_score"] = 0.5
                    scanner_funcs.append(sf)
                
                scanner.set_data(scanner_funcs, rules_list)
                vulnerabilities = scanner.run_all_scans()
            except Exception as e:
                console.print(f"[yellow]Warning: could not run security scanner: {e}[/yellow]")

            # 7. Export symbols
            console.print("Exporting enriched symbols...")
            all_warnings = []
            for f in funcs:
                name = f.get("name")
                parsed_genome = parser.parse_genome(f)
                if parsed_genome.get("warnings"):
                    all_warnings.append({
                        "name": name,
                        "file": parsed_genome.get("file"),
                        "warnings": parsed_genome.get("warnings")
                    })
                
                # Fetch vulnerabilities specific to this symbol
                symbol_vulns = [v for v in vulnerabilities if v.get("function") == name]
                
                start_l = f.get("line")
                end_l = f.get("end_line")
                line_range = [int(start_l), int(end_l)] if (start_l is not None and end_l is not None) else None

                symbol_data = {
                    "name": name,
                    "language": f.get("language") or "generic",
                    "file": f.get("file"),
                    "signature": f.get("signature") or name,
                    "docstring": f.get("docstring"),
                    "params": parsed_genome.get("params", []),
                    "returns": parsed_genome.get("returns", {}),
                    "business_rules": parsed_genome.get("business_rules", []),
                    "code_snippet": f.get("code_snippet"),
                    "mass": cognitive_info.get(name, {}).get("mass", 1.0),
                    "potential_energy": cognitive_info.get(name, {}).get("potential_energy", 0.0),
                    "archetype": cognitive_info.get(name, {}).get("archetype", "generic"),
                    "semantic_neighbors": semantic_neighbors.get(name, []),
                    "callers": calls_map.get(name, {}).get("callers", []),
                    "callees": calls_map.get(name, {}).get("callees", []),
                    "vulnerabilities": symbol_vulns,
                    "line": int(start_l) if start_l is not None else None,
                    "line_range": line_range,
                    "variable_states": f.get("variable_states", {}),
                    "flow_paths": f.get("flow_paths", [])
                }
                engine.export_symbol(symbol_data)
            
            # 8. Export files
            console.print("Exporting file mappings...")
            files_map = {}
            for f in funcs:
                f_path = f.get("file")
                if f_path:
                    files_map.setdefault(f_path, []).append(f)
            
            for f_path, file_funcs in files_map.items():
                lang = file_funcs[0].get("language") or "generic"
                symbols_list = [fn.get("name") for fn in file_funcs if fn.get("name")]
                
                lines_of_code = 0
                size_bytes = 0
                full_path = os.path.join(config.repo_path, f_path)
                if os.path.exists(full_path):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                            lines_of_code = len(file_obj.readlines())
                        size_bytes = os.path.getsize(full_path)
                    except Exception:
                        pass
                else:
                    max_end = 0
                    for fn in file_funcs:
                        el = fn.get("end_line")
                        if el is not None:
                            try:
                                max_end = max(max_end, int(el))
                            except ValueError:
                                pass
                    lines_of_code = max_end if max_end > 0 else 0
                
                # Aggregate file-level variable states from all functions/modules in that file
                file_var_states = {}
                for fn in file_funcs:
                    file_var_states.update(fn.get("variable_states", {}))

                file_data = {
                    "file_path": f_path,
                    "language": lang,
                    "lines_of_code": lines_of_code,
                    "size_bytes": size_bytes,
                    "symbols": symbols_list,
                    "variable_states": file_var_states
                }
                engine.export_file(file_data)
            
            # Export warnings
            engine.export_warnings(all_warnings)
            if all_warnings:
                console.print(f"[yellow]⚠️  Found {len(all_warnings)} docstring/quality warnings! Saved to rules/warnings.md.[/yellow]")
            
            # Export vulnerabilities
            engine.export_vulnerabilities(vulnerabilities)
            if vulnerabilities:
                console.print(f"[red]⚠️  Found {len(vulnerabilities)} security vulnerabilities! Saved to rules/vulnerabilities.md.[/red]")
            
            # Export hotspots & archetypes
            console.print("Exporting cognitive hotspots and archetypes index...")
            try:
                # Hotspots groupings
                complexity_hotspots = sorted(
                    [{"name": k, "file": funcs[0].get("file") if funcs else "unknown", "mass": v["mass"], "archetype": v["archetype"]} for k, v in cognitive_info.items()],
                    key=lambda x: x["mass"],
                    reverse=True
                )[:10]
                attention_hotspots = sorted(
                    [{"name": k, "file": funcs[0].get("file") if funcs else "unknown", "potential_energy": v["potential_energy"], "archetype": v["archetype"]} for k, v in cognitive_info.items()],
                    key=lambda x: x["potential_energy"],
                    reverse=True
                )[:10]
                engine.export_hotspots({"complexity": complexity_hotspots, "attention": attention_hotspots})
                
                # Archetypes groupings
                archetype_groups = {}
                for k, v in cognitive_info.items():
                    arch = v["archetype"]
                    archetype_groups.setdefault(arch, []).append({
                        "name": k,
                        "file": funcs[0].get("file") if funcs else "unknown",
                        "mass": v["mass"],
                        "confidence": 0.95
                    })
                engine.export_archetypes(archetype_groups)
            except Exception as e:
                console.print(f"[yellow]Warning: could not export hotspots/archetypes reports: {e}[/yellow]")

            # 8. BUG-FIX-2: Export behaviors from entrypoints using calls_map
            console.print("Exporting behavior models from entrypoints...")
            try:
                short_to_qualified: dict = {}
                for f in funcs:
                    fname = f.get("name", "")
                    short_to_qualified[fname.split(".")[-1]] = fname
                    short_to_qualified[fname] = fname
                    f_path = f.get("file", "")
                    if f_path:
                        short_to_qualified[f_path] = fname

                sym_meta: dict = {}  # name -> {params, returns, docstring}
                for f in funcs:
                    parsed = parser.parse_genome(f)
                    sym_meta[f.get("name", "")] = {
                        "params": f.get("params") or parsed.get("params", []),
                        "returns": f.get("returns") or parsed.get("returns", {}),
                        "docstring": f.get("docstring") or "",
                    }

                def _make_transition_label(caller_name: str, callee_name: str) -> str:
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
                        rtype = returns.get("type") or (returns if isinstance(returns, str) else "")
                        if rtype:
                            parts.append(f"→{rtype}")
                    return ", ".join(parts) if parts else ""

                finder = EntrypointFinder(repo_path)
                entrypoints = finder.find_entrypoints()

                for ep in entrypoints:
                    ep_short = ep.get("name", "main")
                    ep_path = ep.get("file", "")
                    ep_func = short_to_qualified.get(ep_path, short_to_qualified.get(ep_short, ep_short))

                    callees_from_map = calls_map.get(ep_func, {}).get("callees", [])
                    if not callees_from_map:
                        try:
                            trace = indexer.trace_call_path(ep_func)
                            if isinstance(trace, dict) and trace.get("callees"):
                                callees_from_map = [c["name"] for c in trace["callees"] if isinstance(c, dict) and c.get("name")]
                        except Exception: pass

                    if not callees_from_map:
                        continue

                    states: set = {ep_func}
                    transitions = []
                    visited: set = {ep_func}
                    queue = list(callees_from_map)
                    depth_map = {c: 1 for c in callees_from_map}
                    
                    while queue:
                        current = queue.pop(0)
                        states.add(current)
                        depth = depth_map.get(current, 1)
                        label = _make_transition_label(ep_func, current)
                        parent = ep_func if depth == 1 else None
                        if parent is None:
                            for caller_name, cmap in calls_map.items():
                                if current in cmap.get("callees", []) and caller_name in states:
                                    parent = caller_name
                                    break
                        if parent:
                            transitions.append({"from": parent, "to": current, "condition": label or None})
                        if depth < 3 and current not in visited:
                            visited.add(current)
                            next_callees = calls_map.get(current, {}).get("callees", [])
                            for nc in next_callees:
                                if nc not in visited:
                                    depth_map[nc] = depth + 1
                                    queue.append(nc)

                    built_state_meta = {}
                    for s in states:
                        built_state_meta[s] = sym_meta.get(s, {})

                    behavior_data = {
                        "name": f"{ep_path}-flow",
                        "states": list(states),
                        "transitions": transitions,
                        "state_meta": built_state_meta
                    }
                    engine.export_behavior(behavior_data)
            except Exception as e:
                console.print(f"[yellow]Warning: could not export behaviors from entrypoints: {e}[/yellow]")

            # 9. Final branch diff scouter
            try:
                # BranchDiff needs config and embedder
                embedder = Embedder()
                diff_tool = BranchDiff(config, embedder)
                # Default to comparing HEAD with main
                diff_summary = diff_tool.compare_branches("HEAD", "main")
                engine.export_branch_diff(diff_summary)
            except Exception as e:
                console.print(f"[yellow]Warning: could not compute branch diff: {e}[/yellow]")
                console.print(f"[yellow]Warning: could not compute branch diff: {e}[/yellow]")

            console.print("[green]Obsidian Vault synchronized successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error during librarian sync:[/red] {e}")
        import traceback
        logger.error(traceback.format_exc())
