"""
brain/dependency_mapper.py
Maps external imports, internal module references, and API calls into DependencyNode objects.
Queries the codebase-memory-mcp graph for Import/Require/Call nodes and writes
DEPENDS_ON / IMPORTS / CALLS_API edges back to the graph.
"""
import re
from typing import Any, Dict, List, Optional
from brain.indexer import Indexer


# Allowed dependency types
VALID_DEP_TYPES = {"external", "internal", "api"}


class DependencyNode:
    """Represents a dependency relationship discovered from the MCP graph."""

    def __init__(self, name: str, dep_type: str, source_file: str, target: str):
        if dep_type not in VALID_DEP_TYPES:
            raise ValueError(
                f"Invalid dep_type '{dep_type}'. Must be one of: {VALID_DEP_TYPES}"
            )
        self.name = name
        self.dep_type = dep_type
        self.source_file = source_file
        self.target = target

    def __repr__(self) -> str:
        return f"DependencyNode({self.name!r}, type={self.dep_type!r}, from={self.source_file!r})"


def _classify_dep_type(record: Dict[str, Any]) -> str:
    """
    Classify a raw MCP record as 'external', 'internal', or 'api'.

    Logic:
    - If type contains "API", "HTTP", or target starts with "http" → "api"
    - If target starts with './' or '../' → "internal"
    - Otherwise → "external"
    """
    rec_type = (record.get("type") or "").lower()
    target = (record.get("target") or record.get("name") or "").lower()

    if "api" in rec_type or "http" in rec_type or target.startswith("http://") or target.startswith("https://"):
        return "api"
    if target.startswith("./") or target.startswith("../"):
        return "internal"
    if "relative" in rec_type:
        return "internal"
    return "external"


class DependencyMapper:
    """
    Queries the MCP graph for dependency nodes (imports, requires, API calls)
    and maps them into DependencyNode objects for edge-writing and summarization.
    """

    # Cypher query to retrieve all Import/Require/Call nodes from the graph
    _IMPORT_QUERY = (
        "MATCH (d) "
        "WHERE d:Import OR d:ExternalImport OR d:StdlibImport OR d:RelativeImport "
        "   OR d:SolidityImport OR d:Require OR d:APICall OR d:HTTPCall "
        "RETURN d.name AS name, labels(d)[0] AS type, d.file AS file, d.target AS target"
    )

    def __init__(self, indexer: Indexer):
        self.indexer = indexer

    def _normalize_results(self, raw) -> List[Dict[str, Any]]:
        """Handle both list and {results: [...]} dict formats from query_graph."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("results", [])
        return []

    def get_dependencies(self) -> List[DependencyNode]:
        """
        Query the MCP graph and return all DependencyNode objects found.
        """
        raw = self.indexer.query_graph(self._IMPORT_QUERY)
        records = self._normalize_results(raw)

        deps: List[DependencyNode] = []
        for rec in records:
            try:
                name = rec.get("name") or ""
                source_file = rec.get("file") or ""
                target = rec.get("target") or name
                dep_type = _classify_dep_type(rec)
                deps.append(DependencyNode(name=name, dep_type=dep_type, source_file=source_file, target=target))
            except (ValueError, KeyError):
                # Skip malformed records
                continue
        return deps

    def write_to_graph(self, deps: List[DependencyNode]) -> None:
        """
        Write dependency edges to the MCP graph.
        - external/internal imports → DEPENDS_ON / IMPORTS edge
        - api calls → CALLS_API edge
        """
        if not deps:
            return

        # Build batch Cypher: merge dependency nodes and create edges
        merge_statements: List[str] = []
        edge_statements: List[str] = []

        for i, dep in enumerate(deps):
            var = f"d{i}"
            edge_type = "CALLS_API" if dep.dep_type == "api" else "DEPENDS_ON"
            # Escape single quotes
            safe_name = dep.name.replace("'", "\\'")
            safe_file = dep.source_file.replace("'", "\\'")
            safe_target = dep.target.replace("'", "\\'")

            merge_statements.append(
                f"MERGE ({var}:Dependency {{name: '{safe_name}', type: '{dep.dep_type}', target: '{safe_target}'}})"
            )
            edge_statements.append(
                f"MERGE (src{i}:File {{path: '{safe_file}'}}) "
                f"MERGE (src{i})-[:{edge_type}]->({var})"
            )

        # Execute as two batched calls: one to merge nodes, one for edges
        node_cypher = " ".join(merge_statements)
        edge_cypher = " ".join(edge_statements)

        self.indexer.query_graph(node_cypher)
        self.indexer.query_graph(edge_cypher)

    def build_dependency_summary(self, deps: List[DependencyNode]) -> Dict[str, List[DependencyNode]]:
        """
        Group DependencyNodes by source file for summary output.

        Returns: {source_file: [DependencyNode, ...]}
        """
        summary: Dict[str, List[DependencyNode]] = {}
        for dep in deps:
            key = dep.source_file or "unknown"
            summary.setdefault(key, []).append(dep)
        return summary
