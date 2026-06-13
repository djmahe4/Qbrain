import os
import yaml
import typer
from typing import Optional
from brain.config import Config
from brain.indexer import Indexer

def index_repo(path: Optional[str], config: Config, indexer: Indexer, console):
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
