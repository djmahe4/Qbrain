import os
import json
import subprocess
import re
import shutil
import sys
from typing import Dict, Any, List, Optional
from brain.logger import get_logger

logger = get_logger(__name__)

from brain.persistence_manager import PersistenceManager

from brain.config import Config

class Indexer:
    def __init__(self, config: Config):
        self.config = config
        self._project_name: Optional[str] = None
        
        # Initialize dual-persistence manager
        p_name = self._get_project_name()
        db_path = os.path.join(config.repo_path, f".qbrain-mind-{p_name}.sqlite")
        self.persistence = PersistenceManager(db_path, self)



    def _get_project_name(self) -> str:
        """Resolve the project name for the current repository."""
        if self._project_name:
            return self._project_name
        
        target_path = self.config.repo_path.replace("\\", "/").rstrip("/")
        # Heuristic name used as a first guess to avoid immediate API call in every method
        heuristic_name = re.sub(r'[^a-zA-Z0-9]+', '-', target_path).strip("-")
        
        # We'll stick with heuristic name for now to keep subprocess calls predictable
        # and only use list_projects if heuristic fails or for specific complex scenarios
        self._project_name = heuristic_name
        return self._project_name

    def _run_cli(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Runs codebase-memory-mcp tool via the CLI interface.
        """
        binary = self.config.cbm_binary
        # Security check: Use absolute path if possible
        resolved_binary = shutil.which(binary)
        if resolved_binary:
             # Ensure the resolved path is actually one of the allowed binaries
             binary_basename = os.path.basename(resolved_binary).lower()
        else:
             binary_basename = os.path.basename(binary).lower()

        allowed_binaries = {"codebase-memory-mcp", "cbm-cli", "qbrain-helper"}
        
        if binary_basename.endswith((".exe", ".cmd", ".bat")):
            binary_basename = os.path.splitext(binary_basename)[0]
            
        if binary_basename not in allowed_binaries and not os.environ.get("QBRAIN_ALLOW_UNSAFE_BINARY"):
            raise RuntimeError(
                f"Security Risk: Unrecognized or unauthorized binary '{binary}'. "
                f"Allowed binaries are: {', '.join(allowed_binaries)}."
            )

        exec_binary = resolved_binary or binary
        args_str = json.dumps(args)
        cmd = [exec_binary, "cli", tool_name, args_str]

        logger.info(f"Running Indexer CLI tool: {tool_name}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8"
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as err:
            raise RuntimeError(
                f"Error running codebase-memory-mcp: {err.stderr or err.stdout}"
            ) from err
        except FileNotFoundError as err:
            raise RuntimeError(
                f"Could not find codebase-memory-mcp binary '{exec_binary}'."
            ) from err

    def index_repository(self, repo_path: Optional[str] = None) -> Dict[str, Any]:
        """Trigger a re-index of the repository."""
        target = (repo_path or self.config.repo_path).replace("\\", "/")
        res = self._run_cli("index_repository", {"repo_path": target})
        try:
            data = json.loads(res)
            if "project" in data:
                self._project_name = data["project"]
            return data
        except json.JSONDecodeError:
            return {"raw_result": res}

    def detect_changes(self, repo_path: Optional[str] = None) -> Dict[str, Any]:
        """Run the detect_changes tool."""
        project = self._get_project_name()
        res = self._run_cli("detect_changes", {"project": project})
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"raw_result": res}

    def query_graph(self, cypher_query: str) -> List[Dict[str, Any]]:
        """Run a cypher-like query and return results as a list of dicts."""
        project = self._get_project_name()
        res = self._run_cli("query_graph", {"query": cypher_query, "project": project})
        try:
            data = json.loads(res)
            # Handle standard {"columns": [], "rows": [[]]} format
            if isinstance(data, dict) and "columns" in data and "rows" in data:
                cols = data["columns"]
                rows = data["rows"]
                records = []
                for row in rows:
                    rec = dict(zip(cols, row))
                    # Automatically parse JSON-encoded strings in values (like labels lists)
                    for k, v in rec.items():
                        if isinstance(v, str) and v.startswith("[") and v.endswith("]"):
                            try:
                                rec[k] = json.loads(v)
                            except:
                                pass
                    records.append(rec)
                return records
            # Handle {"results": []} format or raw list
            if isinstance(data, dict):
                return data.get("results", [])
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []

    def list_projects(self) -> Dict[str, Any]:
        """List all indexed projects."""
        res = self._run_cli("list_projects", {})
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"projects": []}

    def get_functions_with_docstrings(self) -> List[Dict[str, Any]]:
        """Fetch all functions with docstrings."""
        project = self._get_project_name()
        res = self._run_cli("get_functions_with_docstrings", {"project": project})
        try:
            data = json.loads(res)
            return data.get("functions", [])
        except json.JSONDecodeError:
            return []

    def get_code_snippet(self, qualified_name: str, project: Optional[str] = None, context_lines: int = 0) -> Dict[str, Any]:
        """Fetch code snippet for a symbol."""
        p_name = project or self._get_project_name()
        res = self._run_cli("get_code_snippet", {
            "qualified_name": qualified_name, 
            "project": p_name,
            "context_lines": context_lines
        })
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"code": ""}

    def get_architecture(self, project: Optional[str] = None) -> Dict[str, Any]:
        """Fetch high-level architecture."""
        p_name = project or self._get_project_name()
        res = self._run_cli("get_architecture", {"project": p_name})
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"raw_result": res}

    def trace_call_path(self, symbol_name: str, direction: str = "both", project: Optional[str] = None) -> Dict[str, Any]:
        """Trace the call path for a symbol."""
        p_name = project or self._get_project_name()
        res = self._run_cli("trace_call_path", {
            "symbol_name": symbol_name,
            "direction": direction,
            "project": p_name
        })
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"raw_result": res}
