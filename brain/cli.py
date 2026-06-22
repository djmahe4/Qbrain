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
from brain.commands import index as index_cmd
from brain.commands import monitor as monitor_cmd
from brain.commands import query as query_cmd
from brain.commands import library as library_cmd
from brain.commands import audit as audit_cmd
from brain.commands import init as init_cmd
from brain.evidence_store import EvidenceStore
from brain.cem_engine import CEMEngine
from brain.san_engine import SANEngine
from brain.cognitive_layer import CognitiveLayer
from brain.narrative_api import NarrativeAPI


app = typer.Typer(
    help="Quantum Brain (qbrain) — Codebase Semantic Gravity Engine",
    add_completion=False,
    no_args_is_help=True
)
console = Console()


def get_engine(repo_path: Optional[str] = None):
    if not repo_path:
        global_config_path = os.path.expanduser("~/.qbrain_global.json")
        if os.path.exists(global_config_path):
            try:
                with open(global_config_path, "r", encoding="utf-8") as f:
                    gdata = json.load(f)
                    active = gdata.get("active_repo")
                    if active and os.path.exists(active):
                        local_config = os.path.join(os.getcwd(), ".quantum-brain.json")
                        if not os.path.exists(local_config) or "quant-blm" in os.path.abspath(os.getcwd()):
                            repo_path = active
            except Exception:
                pass

    config_path = ".quantum-brain.json"
    if repo_path:
        config_path = os.path.join(os.path.abspath(repo_path), ".quantum-brain.json")
    config = Config(config_path)
    if repo_path:
        config.repo_path = os.path.abspath(repo_path)
    indexer = Indexer(config)
    embedder = Embedder(config.embedder_model)
    scorer = QuantumScorer(config, indexer)
    return config, indexer, embedder, scorer

def get_cognitive_engine(repo_path: Optional[str] = None):
    config, indexer, embedder, scorer = get_engine(repo_path)
    os.makedirs(config.metadata_dir, exist_ok=True)
    store = EvidenceStore(os.path.join(config.metadata_dir, "qbrain-evidence.jsonl"))
    cem = CEMEngine()
    san = SANEngine()
    cognitive = CognitiveLayer()
    api = NarrativeAPI(store, cem, san, cognitive)
    return config, indexer, embedder, scorer, store, cem, san, cognitive, api

@app.command()
def init(
    repo_path: str = typer.Option(".", "--repo", "-r", help="Path to the repository to index"),
    vault_path: str = typer.Option("obsidian_vault", "--vault", "-v", help="Path to the Obsidian vault directory")
):
    """Initialize the configuration file (.quantum-brain.json) and index the repository."""
    init_cmd.init_project(repo_path, vault_path, console)

@app.command()
def index(path: Optional[str] = typer.Argument(None, help="Path to index")):
    """Index the repository to populate codebase-memory-mcp graph."""
    config, indexer, _, _ = get_engine(path)
    index_cmd.index_repo(path, config, indexer, console)

@app.command()
def watch(interval: int = typer.Option(5, "--interval", "-i", help="Watcher check interval in minutes")):
    """Start the background git change monitor and physics simulation update loop."""
    config, indexer, embedder, scorer = get_engine()
    monitor_cmd.watch_repo(interval, config, indexer, embedder, scorer, console)

@app.command()
def score(top: int = typer.Option(15, "--top", "-t", help="Number of top functions to return")):
    """Run the quantum N-body gravitational simulation and write values back to the graph."""
    config, indexer, embedder, scorer = get_engine()
    monitor_cmd.score_graph(top, config, indexer, embedder, scorer, console)

@app.command()
def diff(
    base: str = typer.Option("main", "--base", "-b", help="Base branch name"),
    head: str = typer.Option("HEAD", "--head", "-h", help="Head branch name")
):
    """Compare base and head branch to calculate semantic changes and file deltas."""
    config, _, embedder, _ = get_engine()
    query_cmd.diff_branches(base, head, config, embedder, console)

@app.command()
def docstrings(query_str: str = typer.Argument(..., metavar="QUERY", help="Query to match against docstrings")):
    """Query the codebase memory graph semantically using text queries."""
    config, _, embedder, _ = get_engine()
    query_cmd.query_docstrings(query_str, config, embedder, console)

@app.command()
def status():
    """Print configuration parameters and current state status."""
    config, indexer, _, _ = get_engine()
    monitor_cmd.print_status(config, indexer, console)

@app.command()
def entangled(function: str = typer.Option(..., "--function", "-f", help="Function name to trace entanglement for")):
    """Find and trace semantic gravity links (entanglement) connected to a specific function."""
    config, indexer, _, _ = get_engine()
    monitor_cmd.trace_entanglement(function, config, indexer, console)

@app.command()
def calibrate(sample: int = typer.Option(50, "--sample", "-s", help="Sample size of functions to evaluate calibration")):
    """Calibrate gravity and repulsion constants to optimize business/utility distribution."""
    config, indexer, embedder, scorer = get_engine()
    monitor_cmd.calibrate_engine(sample, config, indexer, embedder, scorer, console)

@app.command()
def deps():
    """Query and display the dependency map from codebase-memory-mcp graph."""
    config, indexer, _, _ = get_engine()
    query_cmd.show_deps(config, indexer, console)

@app.command()
def rules(top: int = typer.Option(20, "--top", "-t", help="Max rules to display")):
    """Extract and display business logic rules from docstrings in the graph."""
    config, indexer, _, _ = get_engine()
    query_cmd.show_rules(top, config, indexer, console)

@app.command()
def entrypoints():
    """Locate and display main code entrypoints using configurations or fallbacks."""
    config, _, _, _ = get_engine()
    query_cmd.show_entrypoints(config, console)

@app.command()
def projects():
    """List all indexed projects and check if their vault folders are initialized."""
    config, indexer, _, _ = get_engine()
    query_cmd.list_projects(config, indexer, console)

@app.command()
def audit():
    """Scan the codebase memory graph for potential business logic vulnerabilities."""
    config, indexer, _, _ = get_engine()
    audit_cmd.audit_vulnerabilities(config, indexer, console)

@app.command()
def brain(
    symbol_or_query: str = typer.Argument(..., help="Symbol name, general query, or ADR command"),
    diff: bool = typer.Option(False, "--diff", "-d", help="Analyze recent semantic branch differences as context"),
    adr: Optional[str] = typer.Option(None, "--adr", help="Perform ADR action: list, create, get, update"),
    adr_title: Optional[str] = typer.Option(None, "--adr-title", help="ADR Title (for create)"),
    adr_content: Optional[str] = typer.Option(None, "--adr-content", help="ADR Content (for create/update)"),
    adr_id: Optional[str] = typer.Option(None, "--adr-id", help="ADR ID (for get/update)"),
    adr_status: Optional[str] = typer.Option(None, "--adr-status", help="ADR Status (for create/update)")
):
    """
    Query the qbrain cognitive model & local SLM.
    Handles semantic query answering, branch diff reasoning, and ADR tracking.
    """
    from brain.rag.retriever import VaultRetriever
    from brain.branch_diff import BranchDiff
    from brain.slm import QBrainSLM

    config, indexer, embedder, scorer, store, cem, san, cognitive, api = get_cognitive_engine()
    
    # 1. Check if it is a pure ADR operation
    if adr:
        res = indexer.manage_adr(
            action=adr, adr_id=adr_id, title=adr_title, 
            status=adr_status, content=adr_content
        )
        console.print("[bold green]ADR Action Result:[/bold green]")
        console.print(res)
        return

    # 2. Gather context
    context_notes = []
    semantic_diff = None
    
    # RAG lookup
    try:
        retriever = VaultRetriever(config, embedder)
        context_notes = retriever.retrieve(symbol_or_query, top_k=5)
    except Exception:
        pass

    # Diff lookup
    if diff:
        try:
            diff_tool = BranchDiff(config, embedder)
            semantic_diff = diff_tool.compare_branches("HEAD", config.branch_diff_config.get("base_branch", "main"))
        except Exception:
            pass

    # ADR Context
    try:
        adr_list = indexer.manage_adr("get")
    except Exception:
        adr_list = {}

    # 3. Call local SLM with unified prompt
    slm = QBrainSLM(config, retriever, adr_list, semantic_diff)
    response = slm.generate(symbol_or_query, context_notes)
    
    console.print("[bold cyan]qbrain SLM Cognitive Summary:[/bold cyan]")
    # Stream/print output
    console.print(response)

@app.command()
def sleep():
    """Run the cognitive sleep cycle for expensive background consolidation."""
    _, _, _, _, store, cem, san, cognitive, _ = get_cognitive_engine()
    console.print("[yellow]Starting cognitive sleep cycle...[/yellow]")
    res = cognitive.run_sleep_cycle(store, cem, san)
    console.print(f"[green]Sleep cycle complete.[/green]")
    console.print(res)


library_app = typer.Typer(help="Obsidian Vault Exporter & Learning Librarian CLI")
app.add_typer(library_app, name="library")


@library_app.command("sync")
def library_sync(
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Path to the repository to sync"),
    deep: bool = typer.Option(False, "--deep", help="Run Tier 3 tombstone + orphan reconciliation")
):
    """Sync symbols, behaviors, files, changes, rules to Obsidian vault."""
    config, indexer, _, _ = get_engine(repo)
    library_cmd.sync_library(config, indexer, console, deep=deep)


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
    console.print(f"[bold cyan]{banner}[/bold cyan]")
    app()
