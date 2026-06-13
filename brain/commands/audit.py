import typer
import os
from rich.table import Table
from brain.vuln_scanner import VulnerabilityScanner
from brain.docstring_parser import DocstringParser
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.business_logic_mapper import BusinessLogicMapper
from brain.embedder import Embedder

def audit_vulnerabilities(config, indexer, console):
    """Scan the codebase for potential business logic vulnerabilities using optimized analysis."""
    console.print("Starting Optimized Business Logic Audit (CWE Top 40)...")
    
    # 1. Fetch symbols
    console.print("Step 1/4: Retrieving symbols from graph...")
    doc_parser = DocstringParser(indexer)
    raw_funcs = doc_parser.get_functions_with_docstrings()
    
    if not raw_funcs:
        console.print("[yellow]No functions found in the graph. Run 'qbrain index' first.[/yellow]")
        return

    # 2. Compute physics (scores) in-memory
    console.print(f"Step 2/4: Computing business scores for {len(raw_funcs)} functions...")
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
    # threshold = 0.65 or just top 50
    candidates = sorted(nodes, key=lambda x: x.business_score, reverse=True)[:100]
    console.print(f"Step 3/4: Fetching code snippets for {len(candidates)} high-relevance symbols...")
    
    enriched_funcs = []
    with typer.progressbar(candidates, label="Fetching snippets") as progress:
        for node in progress:
            # We use qualified_name if available, otherwise name
            # But get_code_snippet expects qualified_name
            q_name = node.name 
            # Look up in raw_funcs to find qualified_name if it exists
            orig = next((f for f in raw_funcs if f["name"] == node.name), {})
            q_name = orig.get("qualified_name") or node.name
            
            snippet_res = indexer.get_code_snippet(q_name)
            code = snippet_res.get("code") or ""
            
            enriched_funcs.append({
                "name": node.name,
                "business_score": node.business_score,
                "mass": node.mass,
                "isExported": node.is_exported,
                "file": node.file,
                "code_snippet": code,
                "docstring": getattr(node, "docstring", "")
            })

    # 4. Extract business rules for candidates
    console.print("Step 4/4: Mapping business logic rules and scanning...")
    mapper = BusinessLogicMapper(indexer)
    from brain.language_parser import LanguageParser
    lang_parser = LanguageParser()
    
    all_rules = []
    for f_data in enriched_funcs:
        # Re-parse genome with code_snippet for technical markers
        # We need a record that looks like what LanguageParser expects
        record = {
            "name": f_data["name"],
            "file": f_data["file"],
            "code_snippet": f_data["code_snippet"],
            "docstring": f_data["docstring"]
        }
        genome_dict = lang_parser.parse(record)
        rules = mapper.extract_rules(genome_dict)
        all_rules.extend(rules)

    # Run vulnerability scans
    scanner = VulnerabilityScanner(indexer)
    scanner.set_data(enriched_funcs, all_rules)
    vulns = scanner.run_all_scans()
    
    if not vulns:
        console.print("[green]No high-confidence business logic vulnerabilities found.[/green]")
        return

    table = Table(title=f"Potential Business Logic Vulnerabilities ({len(vulns)} found)")
    table.add_column("CWE", style="magenta")
    table.add_column("Severity", style="bold red")
    table.add_column("Function", style="cyan")
    table.add_column("Description")

    for v in vulns:
        table.add_row(
            v["cwe"],
            v["severity"],
            f"{v['function']} ({v.get('file', 'N/A')})",
            v["description"]
        )
    
    console.print(table)
    console.print("\n[yellow]Note:[/yellow] Detections are based on in-memory heuristics. Please verify each finding manually.")
