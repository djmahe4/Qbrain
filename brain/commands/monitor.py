import random
import typer
from rich.table import Table
from brain.git_watcher import GitWatcher
from brain.docstring_parser import DocstringParser
from brain.quantum_scorer import FunctionNode

def watch_repo(interval: int, config, indexer, embedder, scorer, console):
    """Start the background git change monitor and physics simulation update loop."""
    # Override cron config for current runtime
    config.data["cron"]["git_diff_check_interval_minutes"] = interval
    watcher = GitWatcher(config, indexer, scorer, embedder)
    watcher.start()

def score_graph(top: int, config, indexer, embedder, scorer, console):
    """Run the quantum N-body gravitational simulation and write values back to the graph."""
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

def print_status(config, indexer, console):
    """Print configuration parameters and current state status."""
    console.print("[bold]Quantum Brain Status[/bold]")
    console.print(f"Config path: [green]{config.config_path}[/green]")
    console.print(f"Repository location: [green]{config.repo_path}[/green]")
    console.print(f"Embedder Model: [green]{config.embedder_model}[/green]")
    console.print(f"Gravity Constant G: [green]{config.quantum_gravity_constant}[/green]")
    console.print(f"Repulsive Constant k: [green]{config.repulsive_constant}[/green]")

    watcher = GitWatcher(config, indexer, None, None)
    console.print(f"Last processed watch commit: [green]{watcher.get_last_processed_commit() or 'None'}[/green]")

def calibrate_engine(sample: int, config, indexer, embedder, scorer, console):
    """Calibrate gravity and repulsion constants to optimize business/utility distribution."""
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

def trace_entanglement(function: str, config, indexer, console):
    """Find and trace semantic gravity links (entanglement) connected to a specific function."""
    console.print(f"Tracing entanglement for: [cyan]{function}[/cyan]...")
    
    parser = DocstringParser(indexer)
    funcs = parser.get_functions_with_docstrings()
    
    target_f = next((f for f in funcs if f.get("name") == function), None)
    if not target_f:
        console.print(f"[yellow]Function '{function}' not found in the graph. Run 'qbrain index' first.[/yellow]")
        return

    from brain.embedder import Embedder
    from brain.quantum_scorer import FunctionNode, QuantumScorer
    
    embedder = Embedder(config.embedder_model)
    scorer = QuantumScorer(config, indexer)
    
    console.print("Embedding symbols and calculating forces...")
    
    target_genome = parser.build_genome(target_f)
    target_emb = embedder.embed(target_genome)
    target_node = FunctionNode(
        name=target_f.get("name"),
        embedding=target_emb,
        complexity=float(target_f.get("complexity", 1.0) or 1.0),
        side_effects=float(target_f.get("sideEffects", 0.0) or 0.0),
        is_exported=bool(target_f.get("isExported", False))
    )

    entangled = []
    for f in funcs:
        if f.get("name") == function:
            continue
            
        genome = parser.build_genome(f)
        emb = embedder.embed(genome)
        node = FunctionNode(
            name=f.get("name", "unknown"),
            embedding=emb,
            complexity=float(f.get("complexity", 1.0) or 1.0),
            side_effects=float(f.get("sideEffects", 0.0) or 0.0),
            is_exported=bool(f.get("isExported", False)),
            file=f.get("file", "")
        )
        
        dist_sem = Embedder.semantic_distance(target_node.embedding, node.embedding)
        force = scorer.gravitational_force(target_node, node, dist_sem)
        
        if force > 0.5:
            entangled.append({
                "name": node.name,
                "force": force,
                "file": node.file
            })

    if not entangled:
        console.print(f"[yellow]No entangled functions found for '{function}' with force > 0.5.[/yellow]")
        return

    table = Table(title=f"Entangled Nodes (Bound to {function})")
    table.add_column("Symbol", style="cyan")
    table.add_column("Gravity Force (Attraction)", justify="right")
    table.add_column("Location")

    for r in sorted(entangled, key=lambda x: x["force"], reverse=True):
        table.add_row(r["name"], f"{r['force']:.4f}", r["file"])
    console.print(table)
