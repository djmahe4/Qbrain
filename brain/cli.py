import typer
from rich.console import Console
from rich.table import Table
import numpy as np
import random
import os
import yaml
from typing import Optional

from brain.config import Config
from brain.indexer import Indexer
from brain.embedder import Embedder
from brain.docstring_parser import DocstringParser
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.git_watcher import GitWatcher
from brain.branch_diff import BranchDiff
from brain.dependency_mapper import DependencyMapper
from brain.business_logic_mapper import BusinessLogicMapper
from brain.language_parser import LanguageParser
from brain.librarian import LibrarianEngine

app = typer.Typer(help="Quantum Brain (qbrain) — Codebase Semantic Gravity Engine")
console = Console()

def get_engine():
    config = Config()
    indexer = Indexer(config)
    embedder = Embedder(config.embedder_model)
    scorer = QuantumScorer(config, indexer)
    return config, indexer, embedder, scorer

@app.command()
def index(path: Optional[str] = typer.Argument(None, help="Path to index")):
    """Index the repository to populate codebase-memory-mcp graph."""
    config, indexer, _, _ = get_engine()
    target = path or config.repo_path
    console.print(f"Indexing repository at: [cyan]{target}[/cyan]")
    try:
        git_dir = os.path.join(target, ".git")
        if not os.path.exists(git_dir):
            console.print(f"[yellow]Git repository not found at {target}. Initializing...[/yellow]")
            import shutil
            import subprocess
            git_bin = shutil.which("git") or "git"
            subprocess.run([git_bin, "init"], cwd=target, check=True)
            console.print("[green]Initialized empty Git repository.[/green]")

            rules_file = os.path.join(target, ".qbrain-rules.yaml")
            if not os.path.exists(rules_file):
                default_rules = {
                    "history": {
                        "keep_threshold": 10,
                        "weights": {
                            "symbol_change": 3,
                            "behavior_change": 5,
                            "security_change": 10,
                            "error_change": 6
                        },
                        "ignore": ["*.md", "package-lock.json"]
                    }
                }
                with open(rules_file, "w", encoding="utf-8") as f:
                    yaml.dump(default_rules, f, default_flow_style=False)
                console.print(f"[green]Created default configuration template at {rules_file}[/green]")

        res = indexer.index_repository(target)
        console.print("[green]Indexing triggered successfully![/green]")
        console.print(res)
    except Exception as e:
        console.print(f"[red]Error indexing:[/red] {e}")

@app.command()
def watch(interval: int = typer.Option(5, "--interval", "-i", help="Watcher check interval in minutes")):
    """Start the background git change monitor and physics simulation update loop."""
    config, indexer, embedder, scorer = get_engine()
    # Override cron config for current runtime
    config.data["cron"]["git_diff_check_interval_minutes"] = interval
    watcher = GitWatcher(config, indexer, scorer, embedder)
    watcher.start()

@app.command()
def score(top: int = typer.Option(15, "--top", "-t", help="Number of top functions to return")):
    """Run the quantum N-body gravitational simulation and write values back to the graph."""
    config, indexer, embedder, scorer = get_engine()
    console.print("Retrieving symbols from graph...")
    parser = DocstringParser(indexer)
    funcs = parser.get_functions_with_docstrings()

    if not funcs:
        console.print("[yellow]No functions found in the graph. Run 'qbrain index' first.[/yellow]")
        return

    console.print(f"Found {len(funcs)} functions. Constructing Docstring Genomes...")
    nodes = []
    for f in funcs:
        genome = parser.build_genome(f)
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

    console.print("Running N-body gravitational collapse simulation...")
    scorer.run_simulation(nodes)
    console.print("Writing simulation scores back to the memory graph...")
    scorer.write_physics_to_graph(nodes)

    # Output table
    table = Table(title="Quantum Brain Scoreboard")
    table.add_column("Rank", justify="center")
    table.add_column("Name", style="cyan")
    table.add_column("Mass", justify="right")
    table.add_column("Energy (U)", justify="right")
    table.add_column("Business Score", justify="right")
    table.add_column("Quantum State", style="magenta")

    sorted_nodes = sorted(nodes, key=lambda x: x.business_score, reverse=True)
    for rank, node in enumerate(sorted_nodes[:top], 1):
        table.add_row(
            str(rank),
            node.name,
            f"{node.mass:.2f}",
            f"{node.potential_energy:.2f}",
            f"{node.business_score:.4f}",
            node.quantum_state
        )
    console.print(table)

@app.command()
def diff(
    base: str = typer.Option("main", "--base", "-b", help="Base branch name"),
    head: str = typer.Option("HEAD", "--head", "-h", help="Head branch name")
):
    """Compare base and head branch to calculate semantic changes and file deltas."""
    config, _, embedder, _ = get_engine()
    console.print(f"Comparing branches: [cyan]{base}[/cyan] (base) -> [cyan]{head}[/cyan] (head)...")
    try:
        engine = BranchDiff(config, embedder)
        # Use the same robust regex validation as BranchDiff internals
        for b in [base, head]:
            engine._validate_branch(b)

        res = engine.compare_branches(head, base)

        console.print(f"\n[bold]Files unique to {head} (added):[/bold] {len(res['added_files'])}")
        for f in res["added_files"][:10]:
            meaning = res["added_meanings"].get(f, "N/A")
            console.print(f" - [green]{f}[/green]: [italic]{meaning[:100]}...[/italic]")

        console.print(f"\n[bold]Files unique to {base} (deleted):[/bold] {len(res['deleted_files'])}")
        for f in res["deleted_files"][:10]:
            console.print(f" - [red]{f}[/red]")

        console.print(f"\n[bold]Semantic Diffs (Changed Files):[/bold] {len(res['semantic_changes'])}")
        table = Table()
        table.add_column("File", style="cyan")
        table.add_column("Semantic Distance", justify="right")
        table.add_column("Status")

        for item in res["semantic_changes"]:
            table.add_row(item["file"], f"{item['distance']:.4f}", item["status"])
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error comparing branches:[/red] {e}")

@app.command()
def docstrings(query: str = typer.Argument(..., help="Query to match against docstrings")):
    """Query the codebase memory graph semantically using text queries."""
    config, _, embedder, _ = get_engine()
    console.print(f"Querying semantically for: [italic]{query}[/italic]...")
    parser = DocstringParser(Indexer(config))
    funcs = parser.get_functions_with_docstrings()

    if not funcs:
        console.print("[yellow]No functions available in graph to search.[/yellow]")
        return

    q_emb = embedder.embed(query)

    results = []
    for f in funcs:
        genome = parser.build_genome(f)
        emb = embedder.embed(genome)
        sim = Embedder.cosine_similarity(q_emb, emb)
        results.append((f, sim))

    results = sorted(results, key=lambda x: x[1], reverse=True)

    table = Table(title=f"Semantic Query Matches for: '{query}'")
    table.add_column("Name", style="cyan")
    table.add_column("Similarity", justify="right")
    table.add_column("File")
    table.add_column("Snippet")

    for f, sim in results[:10]:
        table.add_row(
            f.get("name", "unknown"),
            f"{sim:.4f}",
            f"{f.get('file', 'N/A')}:{f.get('line', '0')}",
            f.get("docstring", "")[:80] + "..."
        )
    console.print(table)

@app.command()
def status():
    """Print configuration parameters and current state status."""
    config, indexer, _, _ = get_engine()
    console.print("[bold]Quantum Brain Status[/bold]")
    console.print(f"Config path: [green]{config.config_path}[/green]")
    console.print(f"Repository location: [green]{config.repo_path}[/green]")
    console.print(f"Embedder Model: [green]{config.embedder_model}[/green]")
    console.print(f"Gravity Constant G: [green]{config.quantum_gravity_constant}[/green]")
    console.print(f"Repulsive Constant k: [green]{config.repulsive_constant}[/green]")

    watcher = GitWatcher(config, indexer, None, None)
    console.print(f"Last processed watch commit: [green]{watcher.get_last_processed_commit() or 'None'}[/green]")

@app.command()
def entangled(function: str = typer.Option(..., "--function", "-f", help="Function name to trace entanglement for")):
    """Find and trace semantic gravity links (entanglement) connected to a specific function."""
    config, indexer, _, _ = get_engine()
    console.print(f"Tracing entanglement for: [cyan]{function}[/cyan]...")
    query = (
        f"MATCH (f:Function)-[r:SEMANTIC_GRAVITY]-(g:Function) "
        f"WHERE f.name = '{function}' "
        f"RETURN g.name AS bound_name, r.force AS force, g.file AS file "
        f"ORDER BY r.force DESC"
    )
    try:
        res = indexer.query_graph(query)
        records = res if isinstance(res, list) else res.get("results", [])

        if not records:
            console.print(f"[yellow]No entangled functions found for '{function}'. Try running 'qbrain score' first.[/yellow]")
            return

        table = Table(title=f"Entangled Nodes (Bound to {function})")
        table.add_column("Symbol", style="cyan")
        table.add_column("Gravity Force (Attraction)", justify="right")
        table.add_column("Location")

        for r in records:
            table.add_row(r.get("bound_name", "unknown"), f"{float(r.get('force', 0.0) or 0.0):.4f}", r.get("file", "N/A"))
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error querying entanglement:[/red] {e}")

@app.command()
def calibrate(sample: int = typer.Option(50, "--sample", "-s", help="Sample size of functions to evaluate calibration")):
    """Calibrate gravity and repulsion constants to optimize business/utility distribution."""
    config, indexer, embedder, scorer = get_engine()
    console.print("Running calibration engine...")
    parser = DocstringParser(indexer)
    funcs = parser.get_functions_with_docstrings()

    if len(funcs) < 5:
        console.print("[yellow]Insufficient functions in graph to run calibration.[/yellow]")
        return

    sample_funcs = random.sample(funcs, min(len(funcs), sample))
    console.print(f"Selected {len(sample_funcs)} symbols for sample runs.")

    # Embed sample
    nodes = []
    for f in sample_funcs:
        genome = parser.build_genome(f)
        emb = embedder.embed(genome)
        node = FunctionNode(
            name=f.get("name", "unknown"),
            embedding=emb,
            complexity=float(f.get("complexity", 1.0) or 1.0),
            side_effects=float(f.get("sideEffects", 0.0) or 0.0),
            is_exported=bool(f.get("isExported", False))
        )
        nodes.append(node)

    # Grid search for G and k_repulse to get ~20% business, ~60% neutral, ~20% utility
    best_G, best_k = scorer.G, scorer.k_repulse
    best_error = 999.0

    # Search space
    G_vals = [0.1, 0.5, 1.0, 2.0, 5.0]
    k_vals = [0.01, 0.05, 0.1, 0.5, 1.0]

    for G in G_vals:
        for k in k_vals:
            scorer.G = G
            scorer.k_repulse = k
            # Copy nodes list with fresh positions
            fresh_nodes = []
            for n in nodes:
                fresh_nodes.append(FunctionNode(n.name, n.embedding, n.complexity, n.side_effects, n.is_exported))

            try:
                scorer.run_simulation(fresh_nodes, iterations=30)
                scores = [fn.business_score for fn in fresh_nodes]
                business_pct = sum(1 for s in scores if s >= 0.65) / len(scores)
                utility_pct = sum(1 for s in scores if s <= 0.25) / len(scores)
                neutral_pct = 1.0 - business_pct - utility_pct

                # Target error: business error from 0.20 + utility error from 0.20
                error = abs(business_pct - 0.20) + abs(utility_pct - 0.20)
                if error < best_error:
                    best_error = error
                    best_G = G
                    best_k = k
            except Exception:
                continue

    console.print(f"[green]Calibration completed![/green]")
    console.print(f"Optimal G: [cyan]{best_G}[/cyan]")
    console.print(f"Optimal k_repulse: [cyan]{best_k}[/cyan]")
    console.print(f"Write these into your [bold].quantum-brain.json[/bold] to apply globally.")


@app.command()
def deps():
    """Query and display the dependency map from codebase-memory-mcp graph."""
    config, indexer, _, _ = get_engine()
    console.print("Querying dependency graph from codebase-memory-mcp...")
    try:
        mapper = DependencyMapper(indexer)
        all_deps = mapper.get_dependencies()
        summary = mapper.build_dependency_summary(all_deps)

        if not all_deps:
            console.print("[yellow]No dependencies found. Run 'qbrain index' first.[/yellow]")
            return

        table = Table(title=f"Dependency Map ({len(all_deps)} dependencies)")
        table.add_column("Source File", style="cyan")
        table.add_column("Dependency", style="green")
        table.add_column("Type", style="magenta")
        table.add_column("Target")

        for source_file, dep_list in summary.items():
            for dep in dep_list:
                table.add_row(source_file, dep.name, dep.dep_type, dep.target[:60])
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error mapping dependencies:[/red] {e}")


@app.command()
def rules(top: int = typer.Option(20, "--top", "-t", help="Max rules to display")):
    """Extract and display business logic rules from docstrings in the graph."""
    config, indexer, _, _ = get_engine()
    console.print("Extracting business logic rules from docstring genomes...")
    try:
        lang_parser = LanguageParser()
        raw_funcs = DocstringParser(indexer).get_functions_with_docstrings()

        if not raw_funcs:
            console.print("[yellow]No functions found. Run 'qbrain index' first.[/yellow]")
            return

        genomes = [lang_parser.parse(f) for f in raw_funcs]
        mapper = BusinessLogicMapper(indexer)
        all_rules = mapper.map_all(genomes)

        if not all_rules:
            console.print("[yellow]No business rules extracted from current graph.[/yellow]")
            return

        table = Table(title=f"Business Logic Rules ({len(all_rules)} total)")
        table.add_column("Function", style="cyan")
        table.add_column("Category", style="magenta")
        table.add_column("Confidence", justify="right")
        table.add_column("Rule Description")

        for rule in sorted(all_rules, key=lambda r: r.confidence, reverse=True)[:top]:
            table.add_row(
                rule.source_function,
                rule.category,
                f"{rule.confidence:.2f}",
                rule.description[:80]
            )
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error extracting rules:[/red] {e}")


@app.command()
def entrypoints():
    """Locate and display main code entrypoints using configurations or fallbacks."""
    config = Config()
    repo_path = config.repo_path
    console.print(f"Scanning entrypoints for repository at: [cyan]{repo_path}[/cyan]")
    try:
        from brain.entrypoint_finder import EntrypointFinder
        finder = EntrypointFinder(repo_path)
        results = finder.find_entrypoints()

        if not results:
            console.print("[yellow]No entrypoints found.[/yellow]")
            return

        table = Table(title=f"Codebase Entrypoints ({len(results)} found)")
        table.add_column("Name", style="cyan")
        table.add_column("Type / Config Source", style="magenta")
        table.add_column("Entrypoint Path", style="green")

        for item in results:
            table.add_row(item["name"], item["type"], item["file"])
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error finding entrypoints:[/red] {e}")


@app.command()
def projects():
    """List all indexed projects and check if their vault folders are initialized."""
    config, indexer, _, _ = get_engine()
    console.print("Querying projects from codebase-memory-mcp...")
    try:
        res = indexer.list_projects()
        projects_list = res if isinstance(res, list) else res.get("projects", [])
        
        table = Table(title="Centralized Projects Status")
        table.add_column("Project Name", style="cyan")
        table.add_column("Path", style="green")
        table.add_column("Vault Configured", style="magenta")
        table.add_column("Vault Path")

        for p in projects_list:
            if isinstance(p, dict):
                name = p.get("name", "unknown")
                path = p.get("path", "")
            else:
                name = p
                path = ""
            
            vault_configured = "No"
            project_vault_path = "N/A"
            if path:
                possible_vault = os.path.join(path, "obsidian_vault")
                project_vault_path = possible_vault
                if os.path.exists(os.path.join(possible_vault, "symbols")) and os.path.exists(os.path.join(possible_vault, "files")):
                    vault_configured = "[green]Yes[/green]"
                else:
                    vault_configured = "[red]No[/red]"
            
            table.add_row(name, path or "N/A", vault_configured, project_vault_path)
            
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error listing projects:[/red] {e}")


library_app = typer.Typer(help="Obsidian Vault Exporter & Learning Librarian CLI")
app.add_typer(library_app, name="library")


@library_app.command("sync")
def library_sync():
    """Sync symbols, behaviors, files, changes, rules to Obsidian vault."""
    config, indexer, _, _ = get_engine()
    repo_path = config.repo_path
    vault_path = config.data.get("vault_path", os.path.join(repo_path, "obsidian_vault"))
    
    console.print(f"Syncing librarian from repository [cyan]{repo_path}[/cyan] to vault [cyan]{vault_path}[/cyan]...")
    
    engine = LibrarianEngine(repo_path, vault_path)
    
    try:
        with engine.lock():
            engine.setup_vault()
            
            # Export symbols
            console.print("Exporting symbols...")
            parser = DocstringParser(indexer)
            funcs = parser.get_functions_with_docstrings()
            all_warnings = []
            for f in funcs:
                parsed_genome = parser.parse_genome(f)
                if parsed_genome.get("warnings"):
                    all_warnings.append({
                        "name": parsed_genome.get("name"),
                        "file": parsed_genome.get("file"),
                        "warnings": parsed_genome.get("warnings")
                    })
                symbol_data = {
                    "name": f.get("name"),
                    "language": f.get("language") or "generic",
                    "file": f.get("file"),
                    "signature": f.get("signature") or f.get("name"),
                    "docstring": f.get("docstring"),
                    "params": parsed_genome.get("params", []),
                    "returns": parsed_genome.get("returns", {}),
                    "business_rules": parsed_genome.get("business_rules", [])
                }
                engine.export_symbol(symbol_data)
            
            # Export warnings
            engine.export_warnings(all_warnings)
            if all_warnings:
                console.print(f"[yellow]⚠️  Found {len(all_warnings)} docstring/quality warnings! Saved to vault rules/warnings.md.[/yellow]")
                
            # Export behaviors
            console.print("Exporting behavior models...")
            try:
                behaviors_res = indexer.query_graph("MATCH (b:Behavior) RETURN b")
                behaviors_list = behaviors_res if isinstance(behaviors_res, list) else behaviors_res.get("results", [])
                for b in behaviors_list:
                    engine.export_behavior(b)
            except Exception as e:
                console.print(f"[yellow]Warning: could not load behaviors from graph: {e}[/yellow]")

            console.print("[green]Obsidian Vault synchronized successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error during librarian sync:[/red] {e}")


if __name__ == "__main__":
    app()

