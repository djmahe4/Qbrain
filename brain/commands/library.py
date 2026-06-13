import os
import typer
from brain.librarian import LibrarianEngine
from brain.docstring_parser import DocstringParser

def sync_library(config, indexer, console):
    """Sync symbols, behaviors, files, changes, rules to Obsidian vault."""
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
                snippet_res = indexer.get_code_snippet(f.get("name"))
                f["code_snippet"] = snippet_res.get("code") or ""
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
