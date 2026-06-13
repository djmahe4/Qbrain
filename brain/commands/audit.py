import typer
from rich.table import Table
from brain.vuln_scanner import VulnerabilityScanner

def audit_vulnerabilities(config, indexer, console):
    """Scan the codebase memory graph for potential business logic vulnerabilities."""
    console.print("Scanning codebase for business logic vulnerabilities (CWE Top 40)...")
    
    scanner = VulnerabilityScanner(indexer)
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
    console.print("\n[yellow]Note:[/yellow] These are heuristic-based detections. Please verify each finding manually.")
