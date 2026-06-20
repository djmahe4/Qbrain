import os
import re
import yaml
from typing import Optional

class TaintClassifier:
    """
    Dynamically classifies taint variables into semantic roles.
    Reads user rules from vault's .qbrain/.qbrain-taint-labels.yaml, then falls back
    to graph-role heuristics. Zero hardcoded app values.
    """

    _NAME_PATTERNS = [
        (r"\buser[-_]?id\b",         "USER_ID"),
        (r"\bsession[-_]?id\b",      "SESSION_ID"),
        (r"\btoken\b",               "AUTH_TOKEN"),
        (r"\bpassword|passwd\b",     "CREDENTIAL"),
        (r"\border[-_]?id\b",        "RESOURCE_ID"),
        (r"\bquery\b",               "SQL_SINK"),
        (r"\bcmd|command\b",         "CMD_SINK"),
        (r"\bfile[-_]?path|filename\b", "PATH_SINK"),
        (r"\bheader\b",              "HTTP_HEADER"),
        (r"\binput\b",               "USER_INPUT"),
        (r"\bpayload\b",             "USER_INPUT"),
        (r"\bprice|amount|total\b",  "FINANCIAL_VALUE"),
        (r"\brole|permission\b",     "PRIVILEGE_LABEL"),
    ]

    def __init__(self, metadata_dir: str, registry=None):
        self.registry = registry
        self._user_map: dict = {}
        self._load_user_rules(metadata_dir)

    def _load_user_rules(self, metadata_dir: str):
        """Load overrides from vault's .qbrain/.qbrain-taint-labels.yaml."""
        rules_file = os.path.join(metadata_dir, ".qbrain-taint-labels.yaml")
        if os.path.exists(rules_file):
            try:
                with open(rules_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self._user_map = data.get("labels", {})
            except Exception:
                pass

    def classify(self, var_name: str, graph_role: Optional[str] = None) -> str:
        """
        Returns a semantic label for a variable name.
        Priority: user YAML > graph role > heuristic pattern > "GENERIC_TAINT"
        """
        if not var_name:
            return "GENERIC_TAINT"
            
        # 1. Exact user override
        if var_name in self._user_map:
            return self._user_map[var_name]

        # 2. User pattern override (regex keys)
        for pattern, label in self._user_map.items():
            try:
                if re.search(pattern, var_name, re.IGNORECASE):
                    return label
            except Exception:
                pass

        # 3. Graph role from GlobalRegistry (e.g. var is a known constant → SAFE)
        if self.registry and self.registry.has_constant(var_name):
            return "SAFE_CONSTANT"

        # 4. Heuristic name patterns
        clean = var_name.lstrip("$").lower()
        for pattern, label in self._NAME_PATTERNS:
            if re.search(pattern, clean, re.IGNORECASE):
                return label

        return "GENERIC_TAINT"
