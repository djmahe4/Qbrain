import typer
import os
import sys
import json
from typing import Optional
from rich.console import Console
from brain.config import Config
from brain.indexer import Indexer
from brain.embedder import Embedder
from brain.quantum_scorer import QuantumScorer
from brain.commands import index, monitor, query, library, audit


app = typer.Typer(
    help="Quantum Brain (qbrain) — Codebase Semantic Gravity Engine",
    add_completion=False,
    no_args_is_help=True
)
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
    index.index_repo(path, config, indexer, console)

@app.command()
def watch(interval: int = typer.Option(5, "--interval", "-i", help="Watcher check interval in minutes")):
    """Start the background git change monitor and physics simulation update loop."""
    config, indexer, embedder, scorer = get_engine()
    monitor.watch_repo(interval, config, indexer, embedder, scorer, console)

@app.command()
def score(top: int = typer.Option(15, "--top", "-t", help="Number of top functions to return")):
    """Run the quantum N-body gravitational simulation and write values back to the graph."""
    config, indexer, embedder, scorer = get_engine()
    monitor.score_graph(top, config, indexer, embedder, scorer, console)

@app.command()
def diff(
    base: str = typer.Option("main", "--base", "-b", help="Base branch name"),
    head: str = typer.Option("HEAD", "--head", "-h", help="Head branch name")
):
    """Compare base and head branch to calculate semantic changes and file deltas."""
    config, _, embedder, _ = get_engine()
    query.diff_branches(base, head, config, embedder, console)

@app.command()
def docstrings(query_str: str = typer.Argument(..., metavar="QUERY", help="Query to match against docstrings")):
    """Query the codebase memory graph semantically using text queries."""
    config, _, embedder, _ = get_engine()
    query.query_docstrings(query_str, config, embedder, console)

@app.command()
def status():
    """Print configuration parameters and current state status."""
    config, indexer, _, _ = get_engine()
    monitor.print_status(config, indexer, console)

@app.command()
def entangled(function: str = typer.Option(..., "--function", "-f", help="Function name to trace entanglement for")):
    """Find and trace semantic gravity links (entanglement) connected to a specific function."""
    config, indexer, _, _ = get_engine()
    monitor.trace_entanglement(function, config, indexer, console)

@app.command()
def calibrate(sample: int = typer.Option(50, "--sample", "-s", help="Sample size of functions to evaluate calibration")):
    """Calibrate gravity and repulsion constants to optimize business/utility distribution."""
    config, indexer, embedder, scorer = get_engine()
    monitor.calibrate_engine(sample, config, indexer, embedder, scorer, console)

@app.command()
def deps():
    """Query and display the dependency map from codebase-memory-mcp graph."""
    config, indexer, _, _ = get_engine()
    query.show_deps(config, indexer, console)

@app.command()
def rules(top: int = typer.Option(20, "--top", "-t", help="Max rules to display")):
    """Extract and display business logic rules from docstrings in the graph."""
    config, indexer, _, _ = get_engine()
    query.show_rules(top, config, indexer, console)

@app.command()
def entrypoints():
    """Locate and display main code entrypoints using configurations or fallbacks."""
    config, _, _, _ = get_engine()
    query.show_entrypoints(config, console)

@app.command()
def projects():
    """List all indexed projects and check if their vault folders are initialized."""
    config, indexer, _, _ = get_engine()
    query.list_projects(config, indexer, console)
@app.command()
def audit():
    """Scan the codebase memory graph for potential business logic vulnerabilities."""
    config, indexer, _, _ = get_engine()
    audit.audit_vulnerabilities(config, indexer, console)



library_app = typer.Typer(help="Obsidian Vault Exporter & Learning Librarian CLI")
app.add_typer(library_app, name="library")


@library_app.command("sync")
def library_sync():
    """Sync symbols, behaviors, files, changes, rules to Obsidian vault."""
    config, indexer, _, _ = get_engine()
    library.sync_library(config, indexer, console)


if __name__ == "__main__":
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace"
    )
    banner="""
▄▄▄▄▄  ▄▄▄▄▄  ▄▄▄▄▄ ▄▄▄▄▄  ▄▄ ▄▄▄▄▄ 
▓▓ ▓▓▓ ▓▓ ▓▓▓ ▓▓ ▓▀ ▓▓▓ ▓▓ ▓▓ ▓▓ ▓▓▓
░░ ░░░ ░▀▀░░▄ ░░    ░░▀▀░░ ░░ ░░ ░░░
██▀▄██ ██ ███ ██    ██ ███ ██ ██ ███
▀▓▓▓▓▄ ▓▓▓▓▓▀ ▓▓    ▓▓ ▓▓▓ ▓▓ ▓▓ ▓▓▓

- djmahe4
    """
    
    BLUE_GREEN = "\033[38;2;0;220;200m"
    RESET = "\033[0m"

    sys.stdout.write(BLUE_GREEN + banner + RESET)
    app()

