import typer
import os
from rich.table import Table
from brain.vuln_scanner import VulnerabilityScanner
from brain.docstring_parser import DocstringParser
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.business_logic_mapper import BusinessLogicMapper
from brain.embedder import Embedder
from brain.systemic_auditor import SystemicAuditor
from brain.entrypoint_finder import EntrypointFinder
from brain.language_parser import detect_language

def audit_vulnerabilities(config, indexer, console):
    """Scan the codebase for potential business logic vulnerabilities using optimized analysis."""
    console.print("Starting Optimized Business Logic Audit (CWE Top 40)...")
    
    # 1. Fetch symbols
    console.print("Step 1/5: Retrieving symbols from graph...")
    doc_parser = DocstringParser(indexer)
    raw_funcs = doc_parser.get_functions_with_docstrings()
    
    if not raw_funcs:
        console.print("[yellow]No functions found in the graph. Run 'qbrain index' first.[/yellow]")
        return

    # 2. Compute physics (scores) in-memory
    console.print(f"Step 2/5: Computing business scores for {len(raw_funcs)} functions...")
    embedder = Embedder(config.embedder_model)
    scorer = QuantumScorer(config, indexer)
    
    nodes = []
    for f in raw_funcs:
        genome = doc_parser.build_genome(f)
        emb = embedder.embed(genome)
        node = FunctionNode(
            name=f.get("name", "unknown"),
            embedding=emb,
            complexity=float(f.get("complexity", 1.0) or 1.0),
            side_effects=float(f.get("sideEffects", 0.0) or 0.0),
            is_exported=bool(f.get("isExported", False)),
            file=f.get("file", ""),
            line=int(f.get("line", 0) or 0)
        )
        nodes.append(node)

    # Run simulation in-memory
    scorer.run_simulation(nodes, iterations=30)
    
    # 3. Identify candidates for deep audit and fetch their snippets
    candidates = sorted(nodes, key=lambda x: x.business_score, reverse=True)[:100]
    console.print(f"Step 3/5: Fetching code snippets for {len(candidates)} high-relevance symbols...")
    
    enriched_funcs = []
    with typer.progressbar(candidates, label="Fetching snippets") as progress:
        for node in progress:
            orig = next((f for f in raw_funcs if f["name"] == node.name), {})
            q_name = orig.get("qualified_name") or node.name
            
            code = ""
            try:
                snippet_res = indexer.get_code_snippet(q_name)
                code = snippet_res.get("code") or ""
            except Exception:
                if node.file:
                    full_path = os.path.join(config.repo_path, node.file)
                    if os.path.exists(full_path):
                        try:
                            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                                code = f.read()
                        except Exception: pass
            
            enriched_funcs.append({
                "name": node.name,
                "business_score": node.business_score,
                "mass": node.mass,
                "isExported": node.is_exported,
                "file": node.file,
                "code_snippet": code,
                "docstring": getattr(node, "docstring", ""),
                "language": detect_language(node.file) if node.file else "generic"
            })

    # 4. Extract business rules for candidates
    console.print("Step 4/5: Mapping business logic rules and scanning...")
    mapper = BusinessLogicMapper(indexer)
    from brain.language_parser import LanguageParser
    lang_parser = LanguageParser()
    
    all_rules = []
    for f_data in enriched_funcs:
        record = {
            "name": f_data["name"],
            "file": f_data["file"],
            "code_snippet": f_data["code_snippet"],
            "docstring": f_data["docstring"]
        }
        genome_dict = lang_parser.parse(record)
        rules = mapper.extract_rules(genome_dict)
        all_rules.extend(rules)

    # Run local vulnerability scans
    scanner = VulnerabilityScanner(indexer)
    scanner.set_data(enriched_funcs, all_rules)
    vulns = scanner.run_all_scans()
    
    # 5. Systemic Dataflow Audit
    console.print("Step 5/5: Running Systemic Dataflow Pathfinding...")
    systemic_findings = []
    try:
        calls_map = {}
        calls_res = indexer.query_graph("MATCH (a)-[:CALLS]->(b) RETURN a.name AS caller, b.name AS callee")
        for item in calls_res:
            caller = item.get("caller")
            callee = item.get("callee")
            if caller and callee:
                calls_map.setdefault(caller, {}).setdefault("callees", []).append(callee)
        
        finder = EntrypointFinder(config.repo_path)
        entrypoints = finder.find_entrypoints()
        
        from brain.dataflow_engine import DataFlowEngine
        df_engine = DataFlowEngine()
        for f in enriched_funcs:
            lang = f.get("language") or "php"
            df_res = df_engine.analyze_snippet(f["code_snippet"], lang, file_path=f.get("file", "unknown"))
            f["variable_states"] = df_res.get("variable_states", {})
            f["flow_paths"] = df_res.get("flow_paths", [])

        # Map entrypoints to qualified names in enriched_funcs
        mapped_entrypoints = []
        for ep in entrypoints:
            ep_file = ep.get("file")
            matched = next((f["name"] for f in enriched_funcs if f.get("file") == ep_file), None)
            if matched:
                mapped_entrypoints.append({"name": matched, "file": ep_file})
                continue
            matched = next((f["name"] for f in enriched_funcs if ep_file in f["name"]), None)
            if matched:
                mapped_entrypoints.append({"name": matched, "file": ep_file})
                continue
            matched = next((f["name"] for f in enriched_funcs if f["name"] == ep.get("name")), None)
            if matched:
                mapped_entrypoints.append({"name": matched, "file": ep_file})

        system_auditor = SystemicAuditor(indexer, calls_map, enriched_funcs)
        systemic_findings = system_auditor.audit_all_entrypoints(mapped_entrypoints)
    except Exception as e:
        console.print(f"[yellow]Warning: systemic audit failed: {e}[/yellow]")

    # Reporting
    if not vulns and not systemic_findings:
        console.print("[green]No high-confidence vulnerabilities found.[/green]")
        return

    if vulns:
        table = Table(title=f"Potential Business Logic Vulnerabilities ({len(vulns)} found)")
        table.add_column("CWE", style="magenta")
        table.add_column("Severity", style="bold red")
        table.add_column("Function", style="cyan")
        table.add_column("Description")
        for v in vulns:
            table.add_row(v["cwe"], v["severity"], f"{v['function']} ({v.get('file', 'N/A')})", v["description"])
        console.print(table)

    if systemic_findings:
        table_sys = Table(title=f"Macroscopic Dataflow Findings ({len(systemic_findings)} found)")
        table_sys.add_column("Severity", style="bold red")
        table_sys.add_column("Path")
        table_sys.add_column("Sink")
        for f in systemic_findings:
            table_sys.add_row(f["severity"], f["path"], f"{f['sink']} ({f['variable']})")
        console.print(table_sys)
    
    console.print("\n[yellow]Note:[/yellow] Detections are based on in-memory heuristics. Please verify each finding manually.")
