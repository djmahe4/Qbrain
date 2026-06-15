import os
import typer
from rich.table import Table
from brain.indexer import Indexer
from brain.branch_diff import BranchDiff
from brain.docstring_parser import DocstringParser
from brain.embedder import Embedder
from brain.dependency_mapper import DependencyMapper
from brain.language_parser import LanguageParser
from brain.business_logic_mapper import BusinessLogicMapper

def diff_branches(base: str, head: str, config, embedder, console):
    """Compare base and head branch to calculate semantic changes and file deltas."""
    console.print(f"Comparing branches: [cyan]{base}[/cyan] (base) -> [cyan]{head}[/cyan] (head)...")
    try:
        engine = BranchDiff(config, embedder)
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

def query_docstrings(query: str, config, embedder, console):
    """Query the codebase memory graph semantically using text queries."""
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

def show_deps(config, indexer, console):
    """Query and display the dependency map from codebase-memory-mcp graph."""
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

def show_rules(top: int, config, indexer, console):
    """Extract and display business logic rules from docstrings in the graph."""
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

def show_entrypoints(config, console):
    """Locate and display main code entrypoints using configurations or fallbacks."""
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

def list_projects(config, indexer, console):
    """List all indexed projects and check if their vault folders are initialized."""
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
            
            # Match current repository path if project name corresponds to it
            import re
            current_repo = os.path.abspath(config.repo_path)
            current_name = re.sub(r'[^a-zA-Z0-9]+', '-', current_repo.replace("\\", "/").rstrip("/")).strip("-")
            
            if name.lower() == current_name.lower():
                path = current_repo
            elif not path and "-" in name:
                parts = name.split("-")
                if len(parts) > 1 and len(parts[0]) == 1:
                    possible_path = parts[0] + ":" + os.sep + os.sep.join(parts[1:])
                    if os.path.exists(possible_path):
                        path = possible_path
            
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
