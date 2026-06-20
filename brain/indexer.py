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
        metadata_dir = getattr(config, "metadata_dir", None)
        if not metadata_dir:
            vault_path = getattr(config, "vault_path", os.path.join(config.repo_path, "obsidian_vault"))
            metadata_dir = os.path.abspath(os.path.join(vault_path, ".qbrain"))
        os.makedirs(metadata_dir, exist_ok=True)
        db_path = os.path.join(metadata_dir, f"qbrain-mind-{p_name}.sqlite")
        self.persistence = PersistenceManager(db_path, self)



    def _get_project_name(self) -> str:
        """Resolve the project name for the current repository."""
        name = getattr(self.config, "project_name", "default-project")
        if not isinstance(name, str):
            return "default-project"
        return name

    def _run_cli(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Runs codebase-memory-mcp tool via the CLI interface.
        """
        import sys
        binary = self.config.cbm_binary
        args_str = json.dumps(args)
        if binary in ("codebase-memory-mcp", "codebase_memory_mcp"):
            cmd = [sys.executable, "-m", "codebase_memory_mcp", "cli", tool_name, args_str]
            exec_binary = f"{sys.executable} -m codebase_memory_mcp"
        else:
            # Security check: Use absolute path if possible
            resolved_binary = shutil.which(binary)
            
            # If not found globally, check the current virtual environment's bin/Scripts directory
            if not resolved_binary:
                venv_bin_dir = os.path.dirname(sys.executable)
                possible_path = os.path.join(venv_bin_dir, binary)
                if os.path.exists(possible_path):
                    resolved_binary = possible_path
                elif sys.platform == "win32":
                    for ext in [".exe", ".cmd", ".bat"]:
                        p = os.path.join(venv_bin_dir, binary + ext)
                        if os.path.exists(p):
                            resolved_binary = p
                            break

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
            cmd = [exec_binary, "cli", tool_name, args_str]

        logger.info(f"Running Indexer CLI tool: {tool_name}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                timeout=120  # CWE-400: prevent indefinite blocking on MCP binary hang
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as err:
            raise RuntimeError(
                f"Error running codebase-memory-mcp: {err.stderr or err.stdout}"
            ) from err
        except FileNotFoundError as err:
            raise RuntimeError(
                f"codebase-memory-mcp binary not found at '{exec_binary}'. "
                f"Please ensure it is installed and in your PATH."
            ) from err
        except OSError as err:
            raise RuntimeError(
                f"Failed to execute codebase-memory-mcp binary: {err}"
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
            
            # If it's already a list, return as is
            if isinstance(data, list):
                return data
            
            # Return the raw dict if it doesn't match columns/rows, 
            # to maintain compatibility with tests expecting 'results' or other fields.
            return data
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

    def trace_call_path(self, function_name: str, direction: str = "both", project: Optional[str] = None) -> Dict[str, Any]:
        """Trace the call path for a function."""
        p_name = project or self._get_project_name()
        res = self._run_cli("trace_call_path", {
            "function_name": function_name,
            "direction": direction,
            "project": p_name
        })
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"raw_result": res}
    def search_code(self, pattern: str, project: Optional[str] = None) -> Dict[str, Any]:
        """Search code snippets in the graph using a regex pattern."""
        p_name = project or self._get_project_name()
        res = self._run_cli("search_code", {"pattern": pattern, "project": p_name})
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"results": []}

    def search_graph(self, pattern: str, label: Optional[str] = None, project: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for symbols in the graph."""
        p_name = project or self._get_project_name()
        args = {"query": pattern, "project": p_name}
        if label:
            args["label"] = label
        res = self._run_cli("search_graph", args)
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return []

    def trace_path(self, function_name: str, direction: str = "both", depth: int = 3, project: Optional[str] = None) -> Dict[str, Any]:
        """Trace the call path for a function (Main/Standard tool)."""
        p_name = project or self._get_project_name()
        res = self._run_cli("trace_path", {
            "function_name": function_name,
            "direction": direction,
            "depth": depth,
            "project": p_name
        })
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"path": []}
