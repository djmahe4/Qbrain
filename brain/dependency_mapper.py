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
    ALL_LABELS = _STRUCTURAL_LABELS + _DEPENDENCY_LABELS

    def __init__(self, indexer: Indexer):
        self.indexer = indexer

    def get_dependencies(self) -> List[DependencyNode]:
        """
        Query the MCP graph for dependency nodes and filter in Python.
        Filters out non-code files like READMEs, JSON, etc.
        """
        # Use a broad query that is safe for the parser
        query = "MATCH (d) RETURN d.name AS name, labels(d) AS types, d.file_path AS file, d.target AS target LIMIT 5000"
        records_raw = self.indexer.query_graph(query)
        if isinstance(records_raw, dict):
            records = records_raw.get("results", [])
        elif isinstance(records_raw, list):
            records = records_raw
        else:
            records = []
        
        target_labels = set(self._DEPENDENCY_LABELS)
        excluded_exts = {".md", ".json", ".txt", ".lock", ".log"}
        excluded_names = {"readme", "changelog", "license", "contributors", "authors"}
        
        deps: List[DependencyNode] = []
        for rec in records:
            types = rec.get("types") or []
            path = (rec.get("file") or "").lower()
            name = (rec.get("name") or "").lower()
            
            # Check for excluded files/names
            is_doc = any(path.endswith(ext) for ext in excluded_exts)
            is_meta = any(ex_name in path or ex_name in name for ex_name in excluded_names)
            
            if is_doc or is_meta:
                continue
                
            # Find first matching label
            match = next((t for t in types if t in target_labels), None)
            if match:
                rec["type"] = match
                name = rec.get("name") or ""
                source_file = rec.get("file") or ""
                target = rec.get("target") or name
                
                dep_type = _classify_dep_type(rec)
                deps.append(DependencyNode(name=name, dep_type=dep_type, source_file=source_file, target=target))
        return deps

    def write_to_graph(self, deps: List[DependencyNode]) -> None:
        """
        Write dependency edges to the MCP graph or local sidecar.
        """
        if not deps:
            return
        # 1. Internal Write (Cognitive Persistence)
        for dep in deps:
            self.indexer.persistence.persist_entanglement(
                dep.name, dep.target, dep.dep_type, dep.source_file
            )
            
        logger.info(f"Persisted {len(deps)} dependency links via PersistenceManager.")

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
