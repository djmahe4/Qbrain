"""
brain/dependency_mapper.py
Maps external imports, internal module references, and API calls into DependencyNode objects.
Queries the codebase-memory-mcp graph for Import/Require/Call nodes and writes
DEPENDS_ON / IMPORTS / CALLS_API edges back to the graph.
"""
import re
from typing import Any, Dict, List, Optional
from brain.indexer import Indexer
from brain.logger import get_logger

logger = get_logger(__name__)



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

    # Structural nodes
    _STRUCTURAL_LABELS = [
        "Project", "Package", "Folder", "File", "Module",
        "Class", "Function", "Method", "Interface", "Enum", 
        "Type", "Route", "Resource", "Variable", "Field"
    ]

    # Dependency/Call nodes
    _DEPENDENCY_LABELS = [
        "Import", "ExternalImport", "StdlibImport", "RelativeImport", 
        "SolidityImport", "Require", "APICall", "HTTPCall"
    ]

    # All labels combined
    #ALL_LABELS = _STRUCTURAL_LABELS + _DEPENDENCY_LABELS
    ALL_LABELS = _DEPENDENCY_LABELS

    def __init__(self, indexer: Indexer):
        self.indexer = indexer

    def get_dependencies(self) -> List[DependencyNode]:
        """
        Query the MCP graph for dependency nodes and filter in Python.
        Filters out non-code files like READMEs, JSON, etc.
        """
        # Use a broad query that is safe for the parser
        query = "MATCH (d) RETURN d.name AS name, labels(d) AS types, d.file_path AS file_path, d.file AS file, d.target AS target LIMIT 5000"
        raw = self.indexer.query_graph(query)
        
        # Handle dict response format from mocks or Indexer
        if isinstance(raw, dict) and "results" in raw:
            records = raw["results"]
        elif isinstance(raw, dict) and "rows" in raw:
            # Already normalized by Indexer.query_graph
            records = raw
        else:
            records = raw

        target_labels = set(self._DEPENDENCY_LABELS)
        excluded_exts = {".md", ".json", ".txt", ".yaml", ".yml", ".lock", ".log"}
        excluded_names = {"readme", "changelog", "license", "contributors", "authors"}
        
        deps: List[DependencyNode] = []
        for rec in records:
            # Normalize labels (plural 'types' from real graph, singular 'type' from mocks)
            types = rec.get("types") or []
            if not types and "type" in rec:
                types = [rec["type"]]
                
            # Normalize path (plural 'file_path' from real graph, 'file' from mocks)
            path = (rec.get("file_path") or rec.get("file") or "").lower()
            name = (rec.get("name") or "").lower()
            
            # Check for excluded files/names
            is_doc = any(path.endswith(ext) for ext in excluded_exts)
            is_meta = any(ex_name in path or ex_name in name for ex_name in excluded_names)
            
            if is_doc or is_meta:
                continue
                
            # Find first matching label
            match = next((t for t in types if t in target_labels), None)
            if match:
                rec_for_class = rec.copy()
                rec_for_class["type"] = match
                # Ensure classification uses normalized fields
                rec_for_class["target"] = rec.get("target") or rec.get("name")
                
                name = rec.get("name") or ""
                source_file = rec.get("file_path") or rec.get("file") or ""
                target = rec.get("target") or name
                
                dep_type = _classify_dep_type(rec_for_class)
                deps.append(DependencyNode(name=name, dep_type=dep_type, source_file=source_file, target=target))
        return deps

    def write_to_graph(self, deps: List[DependencyNode]) -> None:
        """
        Write dependency edges to the MCP graph and local sidecar.
        Optimistic write: fails silently with a warning if the graph is read-only.
        """
        if not deps:
            return
            
        # 1. Internal Write (Cognitive Persistence)
        for dep in deps:
            self.indexer.persistence.persist_entanglement(
                dep.name, dep.target, dep.dep_type, dep.source_file
            )
            
        logger.info(f"Persisted {len(deps)} dependency links via PersistenceManager.")

        # 2. External Graph Write
        # Build batch Cypher: merge dependency nodes and create edges
        merge_statements: List[str] = []
        edge_statements: List[str] = []
    def write_to_graph(self, deps: List[DependencyNode]) -> None:
        """
        Persist dependency links to the internal mind (SQLite).
        Graph writes (MERGE) are skipped as they are not supported by codebase-memory-mcp.
        """
        if not deps:
            return
            
        # 1. Internal Write (Cognitive Persistence)
        for dep in deps:
            self.indexer.persistence.persist_entanglement(
                dep.name, dep.target, dep.dep_type, dep.source_file
            )
            
        logger.info(f"Persisted {len(deps)} dependency links to the Internal Mind (SQLite).")

        # Graph updates (MERGE/SET) are currently unsupported and cause failures.
        # We rely on the Librarian to merge SQLite and Graph data during sync.

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
