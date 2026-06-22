import os
import yaml
from typing import Dict, Any, List

class RuleLoader:
    """
    Loads rules, configurations, overrides, and security constraints
    from both YAML configuration files and markdown note files.
    """
    def __init__(self, config):
        self.config = config
        self.metadata_dir = config.metadata_dir
        self.repo_path = config.repo_path
        self.vault_path = config.vault_path

    def load_rules_config(self) -> Dict[str, Any]:
        """Loads rules from the .qbrain-rules.yaml file."""
        rules_path = os.path.join(self.metadata_dir, ".qbrain-rules.yaml")
        if not os.path.exists(rules_path):
            rules_path = os.path.join(self.repo_path, ".qbrain-rules.yaml")
        
        if os.path.exists(rules_path):
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
        return {}

    def load_taint_labels(self) -> Dict[str, Any]:
        """Loads taint labels from .qbrain-taint-labels.yaml."""
        labels_path = os.path.join(self.metadata_dir, ".qbrain-taint-labels.yaml")
        if not os.path.exists(labels_path):
            labels_path = os.path.join(self.repo_path, ".qbrain-taint-labels.yaml")
        
        if os.path.exists(labels_path):
            try:
                with open(labels_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return data.get("labels", {})
            except Exception:
                pass
        return {}

    def load_markdown_rules(self) -> Dict[str, str]:
        """Loads all markdown rules from vault_path/rules/ directory."""
        rules_dir = os.path.join(self.vault_path, "rules")
        markdown_rules = {}
        if os.path.exists(rules_dir):
            for file in os.listdir(rules_dir):
                if file.endswith(".md"):
                    name = os.path.splitext(file)[0]
                    filepath = os.path.join(rules_dir, file)
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            markdown_rules[name] = f.read()
                    except Exception:
                        pass
        return markdown_rules

    def get_consolidated_rules_context(self) -> Dict[str, Any]:
        """Returns a consolidated dictionary of all loaded rules and configurations."""
        return {
            "config_rules": self.load_rules_config(),
            "taint_labels": self.load_taint_labels(),
            "markdown_rules": self.load_markdown_rules()
        }
