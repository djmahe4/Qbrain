import os
import typer
from brain.librarian import LibrarianEngine
from brain.docstring_parser import DocstringParser
from brain.vuln_scanner import VulnerabilityScanner
from brain.entrypoint_finder import EntrypointFinder
from brain.branch_diff import BranchDiff
from brain.embedder import Embedder

def sync_library(config, indexer, console):
    """Sync symbols, behaviors, files, changes, rules to Obsidian vault."""
    repo_path = config.repo_path
    vault_path = config.data.get("vault_path", os.path.join(repo_path, "obsidian_vault"))
    
    console.print(f"Syncing librarian from repository [cyan]{repo_path}[/cyan] to vault [cyan]{vault_path}[/cyan]...")
    
    engine = LibrarianEngine(repo_path, vault_path)
    
    try:
        with engine.lock():
            engine.setup_vault()
            
            # 1. Load cognitive data (mass, potential_energy, archetype) from graph
            console.print("Loading cognitive properties...")
            cognitive_info = {}
            try:
                cog_res = indexer.query_graph(
                    "MATCH (f:Function) "
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
            
            # 2. Query CALLS relationships to build caller/callee entanglements
            console.print("Mapping function entanglements...")
            calls_map = {}
            try:
                calls_res = indexer.query_graph("MATCH (a:Function)-[:CALLS]->(b:Function) RETURN a.name AS caller, b.name AS callee")
                for item in calls_res:
                    caller = item.get("caller")
                    callee = item.get("callee")
                    if caller and callee:
                        calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
                        calls_map.setdefault(callee, {}).setdefault("callers", []).append(caller)
            except Exception as e:
                console.print(f"[yellow]Warning: could not map function calls: {e}[/yellow]")

            # 3. Retrieve functions
            parser = DocstringParser(indexer)
            funcs = parser.get_functions_with_docstrings()
            
            # Retrieve code snippets for all functions
            for f in funcs:
                name = f.get("name")
                snippet_res = indexer.get_code_snippet(name)
                f["code_snippet"] = snippet_res.get("code") or ""
            
            # 4. Generate rules/genome and compute semantic neighbors
            console.print("Computing semantic similarity neighbors...")
            semantic_neighbors = {}
            try:
                embedder = Embedder()
                genomes = [DocstringParser.build_genome(f) for f in funcs]
                if genomes:
                    embeddings = embedder.embed(genomes)
                    for i, f in enumerate(funcs):
                        name = f.get("name")
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
                    "line_range": line_range
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
                
                file_data = {
                    "file_path": f_path,
                    "language": lang,
                    "lines_of_code": lines_of_code,
                    "size_bytes": size_bytes,
                    "symbols": symbols_list
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

            # 8. Export behaviors based on entrypoint call paths
            console.print("Exporting behavior models from entrypoints...")
            try:
                finder = EntrypointFinder(repo_path)
                entrypoints = finder.find_entrypoints()
                for ep in entrypoints:
                    ep_func = ep.get("name", "main")
                    trace = indexer.trace_call_path(ep_func)
                    if trace and trace.get("callees"):
                        states = {ep_func}
                        transitions = []
                        for callee in trace.get("callees", []):
                            cname = callee.get("name")
                            if cname:
                                states.add(cname)
                                if callee.get("hop") == 1:
                                    transitions.append({"from": ep_func, "to": cname})
                        
                        behavior_data = {
                            "name": f"{ep_func}-flow",
                            "states": list(states),
                            "transitions": transitions
                        }
                        engine.export_behavior(behavior_data)
            except Exception as e:
                console.print(f"[yellow]Warning: could not export behaviors from entrypoints: {e}[/yellow]")

            # 9. Export git branch diff report
            console.print("Computing git branch diff...")
            try:
                embedder = Embedder()
                diff_engine = BranchDiff(config, embedder)
                current_branch = diff_engine._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
                base_branch = config.data.get("base_branch", "main")
                
                # Check base_branch reference
                try:
                    diff_engine._run_git(["show-ref", "--verify", f"refs/heads/{base_branch}"])
                    base_exists = True
                except:
                    base_exists = False
                
                if base_exists and current_branch != base_branch:
                    diff_res = diff_engine.compare_branches(current_branch, base_branch)
                    files_diff = []
                    for f in diff_res.get("added", []):
                        files_diff.append({"file": f, "status": "added", "churn": 1, "relevance_score": 5.0})
                    for f in diff_res.get("deleted", []):
                        files_diff.append({"file": f, "status": "deleted", "churn": 1, "relevance_score": 1.0})
                    for item in diff_res.get("semantic_changes", []):
                        files_diff.append({
                            "file": item.get("file"),
                            "status": "modified",
                            "churn": 2,
                            "relevance_score": float(item.get("distance", 0.0) * 10.0)
                        })
                    
                    diff_data = {
                        "target_branch": base_branch,
                        "semantic_distance": float(diff_res.get("average_distance", 0.0)),
                        "files": files_diff
                    }
                    engine.export_branch_diff(diff_data)
            except Exception as e:
                console.print(f"[yellow]Warning: could not compute branch differences: {e}[/yellow]")

            console.print("[green]Obsidian Vault synchronized successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error during librarian sync:[/red] {e}")
