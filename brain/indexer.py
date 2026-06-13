import json
import subprocess
from typing import Dict, Any, Optional
from brain.config import Config

class Indexer:
    def __init__(self, config: Config):
        self.config = config

    def _run_cli(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Runs codebase-memory-mcp tool via the CLI interface.
        Format: <cbm_binary> cli <tool_name> '<args_json>'
        """
        import shutil
        import sys

        binary = self.config.cbm_binary
        resolved_binary = shutil.which(binary)
        if not resolved_binary and sys.platform == "win32":
            for ext in [".cmd", ".bat", ".exe"]:
                r = shutil.which(binary + ext)
                if r:
                    resolved_binary = r
                    break

        exec_binary = resolved_binary or binary
        args_str = json.dumps(args)
        cmd = [exec_binary, "cli", tool_name, args_str]

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
                f"Could not find codebase-memory-mcp binary '{exec_binary}'. "
                "Please ensure it is installed and on your PATH."
            ) from err

    def index_repository(self, repo_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Trigger a re-index of the repository.
        """
        target = repo_path or self.config.repo_path
        res = self._run_cli("index_repository", {"repo_path": target})
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"raw_result": res}

    def detect_changes(self, repo_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the detect_changes tool to map git diffs to symbols.
        """
        target = repo_path or self.config.repo_path
        res = self._run_cli("detect_changes", {"repo_path": target})
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"raw_result": res}

    def query_graph(self, cypher_query: str) -> Dict[str, Any]:
        """
        Run a cypher-like query on the codebase memory graph.
        """
        res = self._run_cli("query_graph", {"query": cypher_query})
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return {"raw_result": res}
