import os
import json
import yaml
import typer
from brain.config import Config
from brain.indexer import Indexer
from brain.librarian import LibrarianEngine

def init_project(repo_path: str, vault_path: str, console) -> None:
    console.print(f"Initializing Qbrain project...")
    
    # 1. Resolve absolute paths
    abs_repo = os.path.abspath(repo_path)
    abs_vault = os.path.abspath(vault_path)
    
    console.print(f"Repository path: [cyan]{abs_repo}[/cyan]")
    console.print(f"Obsidian vault path: [cyan]{abs_vault}[/cyan]")
    
    # Ensure directory exists
    os.makedirs(abs_repo, exist_ok=True)
    
    # 2. Write the .quantum-brain.json file
    config_file = os.path.join(abs_repo, ".quantum-brain.json")
    config_data = {
        "repo_path": abs_repo,
        "vault_path": abs_vault,
        "cbm_binary": "codebase-memory-mcp"
    }
    
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        console.print(f"[green]Created configuration file at {config_file}[/green]")
    except Exception as e:
        console.print(f"[red]Error creating configuration file:[/red] {e}")
        raise typer.Exit(code=1)

    # Write to global config to mark this as the active repository
    global_config = os.path.expanduser("~/.qbrain_global.json")
    try:
        with open(global_config, "w", encoding="utf-8") as f:
            json.dump({"active_repo": abs_repo}, f, indent=2)
        console.print(f"[green]Registered {abs_repo} as globally active Qbrain repository.[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not write global configuration file: {e}[/yellow]")

    # Load config
    config = Config(config_path=config_file)
    indexer = Indexer(config)
    
    # 3. Initialize Git if not present
    git_dir = os.path.join(abs_repo, ".git")
    if not os.path.exists(git_dir):
        console.print(f"[yellow]Git repository not found at {abs_repo}. Initializing...[/yellow]")
        import shutil
        import subprocess
        git_bin = shutil.which("git") or "git"
        try:
            subprocess.run([git_bin, "init"], cwd=abs_repo, check=True)
            console.print("[green]Initialized empty Git repository.[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not initialize Git repository: {e}[/yellow]")
            
    os.makedirs(config.metadata_dir, exist_ok=True)
    rules_file = os.path.join(config.metadata_dir, ".qbrain-rules.yaml")
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
        try:
            with open(rules_file, "w", encoding="utf-8") as f:
                yaml.dump(default_rules, f, default_flow_style=False)
            console.print(f"[green]Created default configuration template at {rules_file}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create default rules template: {e}[/yellow]")

    # 4. Trigger codebase-memory-mcp index_repository
    console.print("Indexing project via codebase-memory-mcp...")
    try:
        res = indexer.index_repository(abs_repo)
        console.print("[green]Indexing triggered successfully![/green]")
        console.print(res)
    except Exception as e:
        console.print(f"[red]Error indexing repository:[/red] {e}")
        
    # 5. Initialize Obsidian Vault directories
    console.print("Setting up Obsidian vault directories...")
    try:
        librarian = LibrarianEngine(abs_repo, abs_vault, indexer=indexer)
        librarian.setup_vault()
        console.print("[green]Obsidian vault folders initialized successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error initializing Obsidian vault folders:[/red] {e}")
