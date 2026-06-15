from brain.logger import get_logger

logger = get_logger(__name__)

import os
import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG = {
    "repo_path": ".",
    "cbm_binary": "codebase-memory-mcp",
    "embedder_model": "all-MiniLM-L6-v2",
    "lru_maxsize": 512,
    "quantum_gravity_constant": 1.0,
    "repulsive_constant": 0.1,
    "business_collapse_threshold": 0.65,
    "cron": {
        "git_diff_check_interval_minutes": 5,
        "branch_lru_sync_interval_minutes": 15,
        "full_reindex_cron": "0 2 * * *"
    },
    "branch_diff": {
        "semantic_drift_threshold": 0.25,
        "lru_branch_pairs_maxsize": 32
    },
    "rules": {
        "history": {
            "keep_threshold": 10,
            "weights": {
                "symbol_change": 3,
                "behavior_change": 5,
                "security_change": 10,
                "error_change": 6
            },
            "ignore": ["*.md", "package-lock.json"]
        }
    }
}


class Config:
    def __init__(self, config_path: str = ".quantum-brain.json"):
        self.config_path = config_path
        self.data = self.load_config()
        self._load_rules_config()

    def _load_rules_config(self):
        repo = self.repo_path
        rules_path = os.path.join(repo, ".qbrain-rules.yaml")
        if os.path.exists(rules_path):
            try:
                import yaml
                with open(rules_path, "r", encoding="utf-8") as f:
                    user_rules = yaml.safe_load(f)
                if user_rules and isinstance(user_rules, dict):
                    self.data["rules"] = self._merge_dicts(self.data.get("rules", {}), user_rules)
            except Exception as e:
                import sys
                logger.warning(f"Failed to parse rules file '{rules_path}': {e}")


    def load_config(self) -> Dict[str, Any]:
        path = Path(self.config_path)
        if not path.is_absolute():
            # Try to resolve relative to current work dir or parents
            curr = Path.cwd()
            resolved_path = curr / path
            if not resolved_path.exists():
                for parent in curr.parents:
                    p = parent / path
                    if p.exists():
                        resolved_path = p
                        break
            path = resolved_path

        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                    # Merge with default config to ensure all fields are present
                    return self._merge_dicts(DEFAULT_CONFIG, user_data)
            except json.JSONDecodeError as e:
                import sys
                print(f"Warning: Failed to parse configuration file '{path}': {e}", file=sys.stderr)
                return DEFAULT_CONFIG.copy()
            except Exception as e:
                import sys
                print(f"Warning: Error reading configuration file '{path}': {e}", file=sys.stderr)
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def _merge_dicts(self, d1: dict, d2: dict) -> dict:
        result = d1.copy()
        for k, v in d2.items():
            if isinstance(v, dict) and k in result and isinstance(result[k], dict):
                result[k] = self._merge_dicts(result[k], v)
            else:
                result[k] = v
        return result

    @property
    def repo_path(self) -> str:
        return os.path.abspath(self.data.get("repo_path", "."))

    @repo_path.setter
    def repo_path(self, value: str):
        self.data["repo_path"] = value

    @property
    def cbm_binary(self) -> str:
        return self.data.get("cbm_binary", "codebase-memory-mcp")

    @property
    def embedder_model(self) -> str:
        return self.data.get("embedder_model", "all-MiniLM-L6-v2")

    @property
    def lru_maxsize(self) -> int:
        return self.data.get("lru_maxsize", 512)

    @property
    def quantum_gravity_constant(self) -> float:
        return self.data.get("quantum_gravity_constant", 1.0)

    @property
    def repulsive_constant(self) -> float:
        return self.data.get("repulsive_constant", 0.1)

    @property
    def business_collapse_threshold(self) -> float:
        return self.data.get("business_collapse_threshold", 0.65)

    @property
    def cron_config(self) -> Dict[str, Any]:
        return self.data.get("cron", DEFAULT_CONFIG["cron"])

    @property
    def branch_diff_config(self) -> Dict[str, Any]:
        return self.data.get("branch_diff", DEFAULT_CONFIG["branch_diff"])
