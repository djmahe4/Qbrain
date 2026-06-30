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

def sync_library(config, indexer, console, deep=False):
    repo_path = config.repo_path
    vault_path = config.vault_path
    if hasattr(vault_path, "_mock_return_value") or not isinstance(vault_path, str):
        if isinstance(getattr(config, "data", None), dict) and "vault_path" in config.data:
            vault_path = config.data["vault_path"]

    
    console.print(f"Syncing librarian from repository [cyan]{repo_path}[/cyan] to vault [cyan]{vault_path}[/cyan]...")
    
    engine = LibrarianEngine(repo_path, vault_path, indexer=indexer)
    
    try:
        with engine.lock():
            engine.setup_vault()
            
            # 1. Retrieve and Qualify Functions
            console.print("Retrieving functions and modules...")
            parser = DocstringParser(indexer)
            funcs = [dict(f) for f in parser.get_functions_with_docstrings()]
            for f in funcs:
                if f.get("file") and f.get("name") and ":" not in f["name"]:
                    f["name"] = f"{f['file']}:{f['name']}"
            
            existing_names = {f["name"] for f in funcs}
            raw_symbols = indexer.query_graph("MATCH (n:Function|Method|Module|Class|Interface|Enum) RETURN n.name AS name, labels(n) AS labels, n.file_path AS file, n.file AS file_alt")
            all_symbols_res = [dict(item) if isinstance(item, dict) else item for item in raw_symbols] if isinstance(raw_symbols, list) else []
            _EXCLUDED_EXTS = {".md", ".json", ".txt", ".yaml", ".yml", ".lock", ".log", ".toml"}
            for item in all_symbols_res:
                s_name = item.get("name")
                f_path = item.get("file") or item.get("file_alt")
                if s_name and f_path:
                    q_name = f"{f_path}:{s_name}"
                    if q_name not in existing_names:
                        if any(f_path.lower().endswith(ext) for ext in _EXCLUDED_EXTS): continue
                        funcs.append({"name": q_name, "file": f_path, "labels": item.get("labels", []), "docstring": "", "language": detect_language(f_path.lower())})
                        existing_names.add(q_name)
            
            short_to_qualified: dict = {}
            for f in funcs:
                fname = f.get("name", "")
                short_to_qualified[fname.split("/")[-1].split(".")[-1]] = fname
                short_to_qualified[fname] = fname
                if f.get("file"): short_to_qualified[f.get("file")] = fname

             # 2. Environmental Pre-Scan (Bootstrap & Global Constants)
            console.print("Executing environmental pre-scan...")
            registry = GlobalRegistry()
            engine.registry = registry
            finder = EntrypointFinder(repo_path)
            setup_files = finder.find_setup_config_files()
            entrypoints = finder.find_entrypoints()
            
            entrypoint_to_behaviors = {}

            for setup_file in setup_files:
                try:
                    with open(setup_file, "r", errors="ignore") as f: content = f.read()
                    rel_path = os.path.relpath(setup_file, repo_path)
                    if setup_file.lower().endswith((".php", ".php.dist")):
                        for name, value in php_parser.extract_globals(content).items():
                            registry.register_constant(name, value, origin=rel_path)
                    elif setup_file.lower().endswith((".env", ".env.dist")):
                        for line in content.splitlines():
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, val = line.split("=", 1)
                                registry.register_env(key.strip(), val.strip().strip("'\""))
                except Exception as e: logger.warning(f"Failed to scan bootstrap file {setup_file}: {e}")

            # 3. Load cognitive data
            console.print("Loading cognitive properties...")
            cognitive_info = {}
            try:
                cog_res = indexer.query_graph("MATCH (f:Function|Method|Module|Class|Interface|Enum) RETURN f.name AS name, f.file_path AS file, f.mass AS mass, f.potential_energy AS potential_energy, f.semantic_archetype AS archetype")
                for item in cog_res:
                    name, f_path = item.get("name"), item.get("file")
                    if name:
                        q_name = f"{f_path}:{name}" if f_path else name
                        cognitive_info[q_name] = {
                            "mass": float(item.get("mass")) if item.get("mass") is not None else 1.0,
                            "potential_energy": float(item.get("potential_energy")) if item.get("potential_energy") is not None else 0.0,
                            "archetype": item.get("archetype") or "generic",
                            "file": f_path or "unknown"
                        }
            except Exception as e: console.print(f"[yellow]Warning: could not load cognitive metadata from graph: {e}[/yellow]")

            try:
                for b in indexer.persistence.get_internal_beliefs():
                    name = b.get("symbol")
                    if name:
                        if ":" not in name:
                            matches = [f["name"] for f in funcs if f["name"].endswith(":" + name)]
                            if len(matches) == 1: name = matches[0]
                        file_from_name = name.split(":")[0] if ":" in name else "unknown"
                        if name not in cognitive_info:
                            cognitive_info[name] = {"mass": b.get("support_mass", 1.0), "potential_energy": b.get("potential_energy", 0.0), "archetype": b.get("winner", "generic"), "file": file_from_name}
                        else:
                            cognitive_info[name].update({"mass": b.get("support_mass", cognitive_info[name]["mass"]), "potential_energy": b.get("potential_energy", cognitive_info[name]["potential_energy"]), "archetype": b.get("winner", cognitive_info[name]["archetype"])})
                            if "file" not in cognitive_info[name]:
                                cognitive_info[name]["file"] = file_from_name
            except Exception as e: console.print(f"[yellow]Warning: could not merge SQLite beliefs: {e}[/yellow]")

            # 4. Query CALLS relationships
            console.print("Mapping function entanglements...")
            calls_map = {}
            try:
                calls_res = indexer.query_graph("MATCH (a)-[:CALLS]->(b) RETURN a.name AS caller, a.file_path AS caller_file, b.name AS callee, b.file_path AS callee_file")
                for item in calls_res:
                    c_name, c_file, ce_name, ce_file = item.get("caller"), item.get("caller_file"), item.get("callee"), item.get("callee_file")
                    if c_name and c_file and ce_name and ce_file:
                        q_caller, q_callee = f"{c_file}:{c_name}", f"{ce_file}:{ce_name}"
                        calls_map.setdefault(q_caller, {}).setdefault("callees", []).append(q_callee)
                        calls_map.setdefault(q_callee, {}).setdefault("callers", []).append(q_caller)
            except Exception as e: console.print(f"[yellow]Warning: could not map function calls from graph: {e}[/yellow]")

            try:
                for ent in indexer.persistence.get_internal_entanglements():
                    src, tgt = ent.get("source"), ent.get("target")
                    if src and tgt:
                        q_src = next((f["name"] for f in funcs if f["name"].endswith(":" + src)), src)
                        q_tgt = next((f["name"] for f in funcs if f["name"].endswith(":" + tgt)), tgt)
                        if q_tgt not in calls_map.get(q_src, {}).get("callees", []):
                            calls_map.setdefault(q_src, {}).setdefault("callees", []).append(q_tgt)
                            calls_map.setdefault(q_tgt, {}).setdefault("callers", []).append(q_src)
            except Exception as e: console.print(f"[yellow]Warning: could not map function entanglements: {e}[/yellow]")

            # 4.5 Discover redirectors dynamically
            console.print("Discovering redirectors...")
            redirectors = []
            try:
                # 1. Functions with "redirect" in name
                redirect_res = indexer.search_graph(".*[Rr]edirect.*", label="Function")
                if isinstance(redirect_res, dict) and redirect_res.get("results"):
                    redirectors.extend([r["name"] for r in redirect_res["results"]])
                
                # 2. Functions containing "header" code (broad search)
                header_res = indexer.search_code("header")
                if isinstance(header_res, dict) and header_res.get("results"):
                    for r in header_res.get("results", []):
                        # We'll refine this by checking for Location in the snippet later or just trust common patterns
                        if r.get("label") in ("Function", "Method"):
                            redirectors.append(r.get("node"))
                
                redirectors = list(set(redirectors))
                if redirectors:
                    console.print(f"Found {len(redirectors)} potential redirector symbols.")
            except Exception as e:
                console.print(f"[yellow]Warning: redirector discovery failed: {e}[/yellow]")

            # 5. Analyze dataflow and detect scenarios
            df_engine = DataFlowEngine()
            scenario_implementations = {}
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
                
                df_res = df_engine.analyze_snippet(f["code_snippet"], lang, registry=registry, file_path=f_path or "unknown", redirectors=redirectors)
                
                f["variable_states"] = df_res.get("variable_states", {})
                f["flow_paths"] = df_res.get("flow_paths", [])
                f["dataflow"] = df_res.get("raw_atoms", [])

                for sync_call in df_res.get("synthesized_calls", []):
                    verb, hint = sync_call.get("verb"), sync_call.get("resolved")
                    if hint:
                        target_node = None
                        clean_hint = hint.replace("{", "").replace("}", "").strip("'\" ")
                        
                        # Normalize clean_hint if it looks like a path
                        normalized_hint = clean_hint.replace("\\", "/")
                        
                        for potential in funcs:
                            p_name = potential.get("name")
                            short_p = p_name.split(":")[-1]
                            if normalized_hint == short_p or p_name.endswith(normalized_hint):
                                target_node = p_name
                                break
                        
                        final_target = target_node or f"[{verb}] {normalized_hint}"
                        scenario_constraints = sync_call.get("scenario_constraints", [])
                        condition = ", ".join(scenario_constraints) if scenario_constraints else None
                        
                        if scenario_constraints:
                            target_file = None
                            if target_node:
                                target_file = next((p.get("file") for p in funcs if p.get("name") == target_node), None)
                            elif "/" in normalized_hint or "." in normalized_hint:
                                # Resolve relative path
                                if f_path:
                                    target_file = os.path.normpath(os.path.join(os.path.dirname(f_path), normalized_hint))
                                else:
                                    target_file = normalized_hint
                            
                            if target_file:
                                target_file = target_file.lstrip("/").replace("\\", "/")
                                dispatcher = f_path or name
                                scenario_implementations.setdefault(dispatcher, [])
                                if not any(s["constraints"] == scenario_constraints for s in scenario_implementations[dispatcher]):
                                    scenario_implementations[dispatcher].append({
                                        "dispatcher": f_path or name,
                                        "constraints": scenario_constraints,
                                        "verb": verb
                                    })

                        if (final_target, condition) not in calls_map.get(name, {}).get("callees_detailed", []):
                            calls_map.setdefault(name, {}).setdefault("callees_detailed", []).append((final_target, condition))
                            calls_map.setdefault(name, {}).setdefault("callees", []).append(final_target)
                        if name not in calls_map.get(final_target, {}).get("callers", []):
                            calls_map.setdefault(final_target, {}).setdefault("callers", []).append(name)

            # 6. Semantic neighbors & PE
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
                        similarities = sorted([(funcs[j].get("name"), Embedder.cosine_similarity(embeddings[i], embeddings[j])) for j in range(len(funcs)) if i != j], key=lambda x: x[1], reverse=True)
                        semantic_neighbors[fname] = similarities[:3]
            except Exception as e: console.print(f"[yellow]Warning: could not calculate semantic neighbors: {e}[/yellow]")

            _pe_mostly_zero = sum(1 for v in cognitive_info.values() if v.get("potential_energy", 0.0) == 0.0) / max(len(cognitive_info), 1) > 0.8 if cognitive_info else True
            if _pe_mostly_zero and _func_embeddings:
                console.print("[dim]Computing potential energy inline...[/dim]")
                try:
                    scorer = QuantumScorer(config, indexer)
                    nodes_for_pe = []
                    for f in funcs:
                        fname = f.get("name")
                        emb = _func_embeddings.get(fname)
                        if emb is not None:
                            nodes_for_pe.append(FunctionNode(name=fname, embedding=emb, complexity=float(f.get("complexity", 1.0) or 1.0), side_effects=float(f.get("sideEffects", 0.0) or 0.0), is_exported=bool(f.get("isExported", False)), file=f.get("file", ""), line=int(f.get("line", 0) or 0)))
                    scorer.run_simulation(nodes_for_pe, iterations=30)
                    for node in nodes_for_pe:
                        if node.name in cognitive_info: cognitive_info[node.name].update({"potential_energy": node.potential_energy, "archetype": node.quantum_state})
                        else: cognitive_info[node.name] = {"mass": node.mass, "potential_energy": node.potential_energy, "archetype": node.quantum_state}
                    scorer.write_physics_to_graph(nodes_for_pe)
                except Exception as e: console.print(f"[yellow]Warning: inline PE computation failed: {e}[/yellow]")

            # 7. Vulnerability Scan
            console.print("Running security scans...")
            vulnerabilities = []
            rules_list = []
            for f in funcs:
                for r in parser.parse_genome(f).get("business_rules", []):
                    desc = r.lower()
                    cat = "authorization" if any(kw in desc for kw in ["auth", "permission"]) else "event" if "event" in desc or "log" in desc else "io" if any(kw in desc for kw in ["read", "write", "file", "db", "query"]) else "validation" if any(kw in desc for kw in ["validate", "check"]) else "generic"
                    rules_list.append({"source_function": f.get("name"), "category": cat, "description": r})

            try:
                scanner = VulnerabilityScanner(indexer)
                enriched_for_scan = []
                for f in funcs:
                    parsed = parser.parse_genome(f)
                    enriched_for_scan.append({
                        **f,
                        "mass": cognitive_info.get(f.get("name"), {}).get("mass", 1.0),
                        "business_score": 0.5,
                        "warnings": parsed.get("warnings", []),
                    })
                scanner.set_data(enriched_for_scan, rules_list)
                for rv in scanner.run_all_scans():
                    v_msg = rv.get("description") or rv.get("message")
                    vulnerabilities.append({"cwe": rv.get("cwe", "CWE-Unknown"), "severity": rv.get("severity", "LOW"), "function": rv.get("function"), "file": rv.get("file", "unknown"), "description": v_msg, "message": v_msg})
            except Exception as e: console.print(f"[yellow]Warning: could not run security scanner: {e}[/yellow]")

            try:
                system_auditor = SystemicAuditor(indexer, calls_map, funcs)
                mapped_eps = []
                for ep in entrypoints:
                    ep_path = ep.get("file", "")
                    q_name = short_to_qualified.get(ep_path) or next((f.get("name") for f in funcs if f.get("file") == ep_path), ep.get("name"))
                    if q_name: mapped_eps.append({"name": q_name, "file": ep_path})
                for sf in system_auditor.audit_all_entrypoints(mapped_eps):
                    v_desc = f"Global flow: {sf['path']} -> {sf['sink']} ({sf['variable']})"
                    start_func = sf["path"].split(" -> ")[0]
                    start_file = next((f.get("file") for f in funcs if f.get("name") == start_func), "unknown")
                    vulnerabilities.append({
                        "cwe": "CWE-Global",
                        "severity": sf["severity"],
                        "function": start_func,
                        "file": start_file,
                        "description": v_desc,
                        "message": v_desc,
                        "safe_link": engine._get_safe_filename(start_func)
                    })
            except Exception as e: console.print(f"[yellow]Warning: systemic audit failed: {e}[/yellow]")
            for v in vulnerabilities: v.setdefault("safe_link", engine._get_safe_filename(v.get("function", "unknown")))

            # 8. Export
            console.print("Exporting enriched vault...")
            all_warnings, file_symbols_data = [], {}

            sym_meta = {f["name"]: {
                "file": f.get("file"),
                "line": int(f.get("line")) if f.get("line") is not None else None,
                "kind": next((k for k in ["Class", "Interface", "Enum", "Variable", "Method", "Function", "Module"] if k in f.get("labels", [])), "Function"),
                "params": f.get("params", []),
                "returns": f.get("returns", {}),
                "docstring": f.get("docstring") or "",
                "potential_energy": cognitive_info.get(f["name"], {}).get("potential_energy", 0.0),
                "archetype": cognitive_info.get(f["name"], {}).get("archetype", "generic"),
                "variable_states": f.get("variable_states", {}),
                "flow_paths": f.get("flow_paths", []),
                "code_snippet": f.get("code_snippet")
            } for f in funcs}

            # 9. Scenarios
            behaviors = []
            symbol_to_behaviors = {}
            file_to_behaviors = {}
            processed_behaviors = set()
            for ep in entrypoints:
                ep_path = ep.get("file", "")
                ep_func = short_to_qualified.get(ep_path) or next((f.get("name") for f in funcs if f.get("file") == ep_path), ep.get("name", "main"))
                scenarios = scenario_implementations.get(ep_path, [])
                if not scenarios:
                    if ep_path in processed_behaviors: continue
                    model = engine.generate_behavior_model(ep_func, ep_path, calls_map, funcs, sym_meta, max_depth=config.data.get("behavior_max_depth", 10), max_states=config.data.get("behavior_max_states", 50))
                    model["name"] = engine._get_safe_filename(ep_path)
                    behaviors.append(model)
                    processed_behaviors.add(ep_path)
                    entrypoint_to_behaviors.setdefault(ep_path, []).append((model["name"], "Behavior Machine"))
                else:
                    max_behaviors = config.data.get("rules", {}).get("behavior_model", {}).get("max_behaviors_per_entrypoint", 8)
                    if len(scenarios) > max_behaviors:
                        from brain.taint_classifier import TaintClassifier
                        metadata_dir = os.path.join(vault_path, ".qbrain")
                        classifier = TaintClassifier(metadata_dir, registry=registry)
                        important = []
                        others = []
                        for scene in scenarios:
                            is_important = False
                            for cond in scene["constraints"]:
                                m = re.search(r"([\$\w]+)", cond)
                                if m:
                                    var = m.group(1)
                                    lbl = classifier.classify(var)
                                    if lbl in ("PRIVILEGE_LABEL", "AUTH_TOKEN", "SESSION_ID", "USER_ID"):
                                        is_important = True
                                        break
                            if is_important:
                                important.append(scene)
                            else:
                                others.append(scene)
                        
                        if len(important) < max_behaviors:
                            scenarios = important + others[:max_behaviors - len(important)]
                        else:
                            scenarios = important[:max_behaviors]

                    for scene in scenarios:
                        constraints = scene["constraints"]
                        scene_label = "_".join(constraints)
                        scene_label = re.sub(r"==\s*['\"]?(\w+)['\"]?", r"\1", scene_label).capitalize()
                        if scene_label == "Default": scene_label = "Impossible"
                        parts = ep_path.split("/")
                        prefix = parts[-3].replace("-", "_").capitalize() if (len(parts) >= 3 and parts[-2] == "source") else os.path.basename(os.path.dirname(ep_path)).replace("-", "_").capitalize()
                        f_base = os.path.splitext(os.path.basename(ep_path))[0].capitalize()
                        behavior_id = f"{prefix}_{f_base}_{scene_label}"
                        if behavior_id in processed_behaviors: continue
                        model = engine.generate_behavior_model(ep_func, ep_path, calls_map, funcs, sym_meta, scenario_constraints=constraints, max_depth=config.data.get("behavior_max_depth", 10), max_states=config.data.get("behavior_max_states", 50))
                        model["name"], model["scenario_context"] = behavior_id, constraints
                        behaviors.append(model)
                        processed_behaviors.add(behavior_id)
                        entrypoint_to_behaviors.setdefault(ep_path, []).append((behavior_id, scene_label))

            for model in behaviors:
                b_name = model["name"]
                for s in model["states"]:
                    symbol_to_behaviors.setdefault(s, []).append(b_name)
                    s_file = sym_meta.get(s, {}).get("file")
                    if s_file:
                        file_to_behaviors.setdefault(s_file, []).append(b_name)

            for f in funcs:
                name, f_path = f.get("name"), f.get("file")
                parsed = parser.parse_genome(f)
                if parsed.get("warnings"): all_warnings.append({"name": name, "file": parsed.get("file"), "warnings": parsed.get("warnings")})
                
                symbol_kind = next((k for k in ["Class", "Interface", "Enum", "Variable", "Method", "Function", "Module"] if k in f.get("labels", [])), "Function")
                symbol_data = {
                    "name": name, "language": f.get("language") or "generic", "file": f_path, "kind": symbol_kind,
                    "signature": f.get("signature") or name, "docstring": f.get("docstring"),
                    "params": parsed.get("params", []), "returns": parsed.get("returns", {}),
                    "business_rules": parsed.get("business_rules", []), "code_snippet": f.get("code_snippet"),
                    "mass": cognitive_info.get(name, {}).get("mass", 1.0), "potential_energy": cognitive_info.get(name, {}).get("potential_energy", 0.0),
                    "archetype": cognitive_info.get(name, {}).get("archetype", "generic"), "semantic_neighbors": semantic_neighbors.get(name, []),
                    "callers": calls_map.get(name, {}).get("callers", []), "callees": calls_map.get(name, {}).get("callees", []),
                    "vulnerabilities": [v for v in vulnerabilities if str(v.get("function")).strip() == str(name).strip()],
                    "line": int(f.get("line")) if f.get("line") is not None else None,
                    "line_range": [int(f.get("line")), int(f.get("end_line"))] if (f.get("line") is not None and f.get("end_line") is not None) else None,
                    "variable_states": f.get("variable_states", {}), "flow_paths": f.get("flow_paths", []),
                    "behaviors": symbol_to_behaviors.get(name, [])
                }
                # Aggregated into files and also exported as individual symbol files for RAG
                if f_path: 
                    file_symbols_data.setdefault(f_path, []).append(symbol_data)
                    engine.export_symbol(symbol_data)


            files_map = {}
            for f in funcs:
                if f.get("file"): files_map.setdefault(f.get("file"), []).append(f)
            
            for f_path, file_funcs in files_map.items():
                full_p = os.path.normpath(f_path if os.path.isabs(f_path) else os.path.join(repo_path, f_path))
                if not os.path.exists(full_p):
                    for r, _, fs in os.walk(repo_path):
                        if os.path.basename(f_path) in fs: full_p = os.path.join(r, os.path.basename(f_path)); break
                loc, sz = 0, 0
                if os.path.exists(full_p):
                    try:
                        with open(full_p, "r", errors="ignore") as fo: loc = len(fo.readlines())
                        sz = os.path.getsize(full_p)
                    except Exception: pass
                f_var_states = {}
                for fn in file_funcs: f_var_states.update(fn.get("variable_states", {}))
                
                # Compute cognitive details for the file
                file_mass = sum(cognitive_info.get(fn.get("name"), {}).get("mass", 1.0) for fn in file_funcs)
                file_pe = sum(cognitive_info.get(fn.get("name"), {}).get("potential_energy", 0.0) for fn in file_funcs) / len(file_funcs) if file_funcs else 0.0
                file_archetypes = list(set(cognitive_info.get(fn.get("name"), {}).get("archetype", "generic") for fn in file_funcs))

                engine.export_file({
                    "file_path": f_path, 
                    "language": file_funcs[0].get("language") or "generic", 
                    "lines_of_code": loc, 
                    "size_bytes": sz, 
                    "symbols": [fn.get("name") for fn in file_funcs if fn.get("name")], 
                    "symbols_data": file_symbols_data.get(f_path, []), 
                    "variable_states": f_var_states,
                    "cognitive_mass": file_mass,
                    "potential_energy": file_pe,
                    "archetypes": file_archetypes,
                    "behaviors": file_to_behaviors.get(f_path, [])
                })

            engine.export_warnings(all_warnings)
            engine.export_prerequisites(setup_files, registry)
            engine.export_vulnerabilities(vulnerabilities)
            engine.export_hotspots({
                "complexity": sorted([{"name": k, "mass": v["mass"], "archetype": v["archetype"], "file": v.get("file", "unknown")} for k, v in cognitive_info.items()], key=lambda x: x["mass"], reverse=True)[:10],
                "attention": sorted([{"name": k, "potential_energy": v["potential_energy"], "archetype": v["archetype"], "file": v.get("file", "unknown")} for k, v in cognitive_info.items()], key=lambda x: x["potential_energy"], reverse=True)[:10]
            })
            
            arch_groups = {}
            for k, v in cognitive_info.items():
                arch_groups.setdefault(v["archetype"], []).append({
                    "name": k,
                    "mass": v["mass"],
                    "potential_energy": v["potential_energy"],
                    "variable_states": next((f.get("variable_states", {}) for f in funcs if f.get("name") == k), {}),
                    "flow_paths": next((f.get("flow_paths", []) for f in funcs if f.get("name") == k), []),
                    "behaviors": symbol_to_behaviors.get(k, []),
                    "confidence": 0.95
                })
            engine.export_archetypes(arch_groups)
            for arch, syms in arch_groups.items(): engine.export_narrative(arch, syms)

            # Export privilege map
            try:
                engine.generate_and_export_privilege_map(funcs, calls_map)
            except Exception as e:
                console.print(f"[yellow]Warning: privilege boundaries mapping failed: {e}[/yellow]")

            for model in behaviors:
                engine.export_behavior(model)

            # Export central entrypoints.md
            entrypoints_path = os.path.join(vault_path, "entrypoints.md")
            os.makedirs(vault_path, exist_ok=True)
            with open(entrypoints_path, "w", encoding="utf-8") as ep_file:
                ep_file.write("# Application Entrypoints\n\n")
                ep_file.write("This page lists all identified entrypoints and their corresponding behavior models.\n\n")
                ep_file.write("| Entrypoint | Source File | Behavior Map |\n")
                ep_file.write("| :--- | :--- | :--- |\n")
                for ep in entrypoints:
                    ep_path_val = ep.get("file", "")
                    ep_name = ep.get("name", "main")
                    
                    associated = entrypoint_to_behaviors.get(ep_path_val, [])
                    if not associated:
                        ep_safe = engine._get_safe_filename(ep_path_val) if ep_path_val else ep_name
                        behavior_link = f"[[behaviors/{ep_safe}\\|Behavior Machine]]"
                    else:
                        links = []
                        for b_id, label in associated:
                            links.append(f"[[behaviors/{b_id}\\|{label}]]")
                        behavior_link = ", ".join(links)
                        
                    ep_file.write(f"| `{ep_name}` | `[files/{ep_path_val}](file:///{os.path.join(repo_path, ep_path_val).replace('\\\\', '/')})` | {behavior_link} |\n")
                ep_file.write("\n")
            try:
                diff_tool = BranchDiff(config, Embedder())
                engine.export_branch_diff(diff_tool.compare_branches("HEAD", config.data.get("branch_diff", {}).get("base_branch") or diff_tool.get_default_branch()))
            except Exception: pass

            # Deep Graph Reconciliation (Sprint 4)
            if deep:
                console.print("Running deep graph-vs-disk reconciliation...")
                from brain.sync_guard import SyncGuard
                guard = SyncGuard()
                drift_events = guard.run_tier3(repo_path, indexer)
                
                # Fetch currently tracked file count
                total_files = len(set(f.get("file") for f in funcs if f.get("file")))
                tombstones = [e.file_path for e in drift_events if e.event_type == "TOMBSTONE"]
                
                if drift_events:
                    engine.export_blackboard_note(drift_events)
                    console.print(f"Exported blackboard note documenting {len(drift_events)} drift events.")
                    
                if guard.should_trigger_repopulation(drift_events, total_files):
                    console.print(f"[yellow]Tombstones exceed threshold ({len(tombstones)} / {total_files}). Triggering selective vault pruning...[/yellow]")
                    engine.prune_stale_pages(tombstones)

            console.print("[green]Obsidian Vault synchronized successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error during librarian sync:[/red] {e}")
        logger.exception("Library sync failed")
