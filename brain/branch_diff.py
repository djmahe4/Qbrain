"""
BranchDiff module for comparing two git branches and identifying added, deleted, and semantically changed files.
"""

import subprocess
import re
from typing import List, Dict, Any, Tuple, Set
from brain.config import Config
from brain.embedder import Embedder

class BranchDiff:
    """
    Class to compare two git branches and identify added, deleted, and semantically changed files.
    """
    def __init__(self, config: Config, embedder: Embedder):
        self.config = config
        self.embedder = embedder

    def _validate_branch(self, branch: str) -> None:
        if not branch or not isinstance(branch, str):
            raise ValueError("Invalid branch name: must be a non-empty string.")
        if branch.startswith("-"):
            raise ValueError(f"Invalid branch name: '{branch}' cannot start with a dash.")
        if not re.match(r"^[a-zA-Z0-9_\-\/\.\+]+$", branch):
            raise ValueError(f"Invalid branch name: '{branch}' contains forbidden characters.")

    def _run_git(self, args: List[str]) -> str:
        repo = self.config.repo_path
        cmd = ["git"] + args
        try:
            res = subprocess.run(
                cmd,
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8"
            )
            return res.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Git command failed: {' '.join(cmd)}\nError: {e.stderr or e.stdout}"
            ) from e

    def get_files_in_branch(self, branch: str) -> Set[str]:
        """Runs git ls-tree to list all files in a branch."""
        self._validate_branch(branch)
        out = self._run_git(["ls-tree", "-r", "--name-only", branch])
        if not out:
            return set()
        return set(out.splitlines())

    def get_file_content(self, branch: str, file_path: str) -> str:
        """Runs git show to get file contents at a specific branch version."""
        self._validate_branch(branch)
        try:
            return self._run_git(["show", f"{branch}:{file_path}"])
        except Exception:
            return ""

    def compare_branches(self, branch_x: str, branch_y: str) -> Dict[str, Any]:
        """
        Compare branch X (head/feature) and branch Y (base/main).
        Finds:
        - Files in X but not Y (added in X)
        - Files in Y but not X (deleted in X)
        - Common files with semantic changes (distance > threshold)
        """
        self._validate_branch(branch_x)
        self._validate_branch(branch_y)
        files_x = self.get_files_in_branch(branch_x)
        files_y = self.get_files_in_branch(branch_y)

        added = files_x - files_y
        deleted = files_y - files_x
        common = files_x & files_y

        # Summarize meanings of added files
        added_meanings: Dict[str, str] = {}
        for f in list(added)[:15]:  # Limit to first 15 files to prevent excessive encoding
            content = self.get_file_content(branch_x, f)
            if content.strip():
                # Summarize meaning or save first 200 characters for embedding
                added_meanings[f] = content[:300].replace("\n", " ").strip()

        # Compute semantic drift for common files
        semantic_changes: List[Dict[str, Any]] = []
        drift_threshold = self.config.branch_diff_config.get("semantic_drift_threshold", 0.25)

        for f in common:
            # Only check files that typically contain code (e.g. .py, .js, .ts)
            if not any(f.endswith(ext) for ext in [".py", ".js", ".ts", ".tsx", ".jsx", ".go"]):
                continue

            content_x = self.get_file_content(branch_x, f)
            content_y = self.get_file_content(branch_y, f)

            if content_x == content_y or not content_x.strip() or not content_y.strip():
                continue

            # Compute embeddings of file contents (or docstring if we want simple file comparison)
            emb_x = self.embedder.embed(content_x[:2000])  # Cap content length for embedder efficiency
            emb_y = self.embedder.embed(content_y[:2000])

            distance = Embedder.semantic_distance(emb_x, emb_y)
            if distance >= drift_threshold:
                semantic_changes.append({
                    "file": f,
                    "distance": distance,
                    "status": "semantically_diverged"
                })

        return {
            "branch_x": branch_x,
            "branch_y": branch_y,
            "added_files": list(added),
            "added_meanings": added_meanings,
            "deleted_files": list(deleted),
            "semantic_changes": sorted(semantic_changes, key=lambda x: x["distance"], reverse=True)
        }
