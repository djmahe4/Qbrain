import os
import yaml
import pytest
from brain.config import Config
from brain.rule_loader import RuleLoader

def test_rule_loader_basic(tmp_path):
    # Create mock directories
    vault_dir = tmp_path / "obsidian_vault"
    vault_dir.mkdir()
    metadata_dir = vault_dir / ".qbrain"
    metadata_dir.mkdir()
    rules_dir = vault_dir / "rules"
    rules_dir.mkdir()

    # Create dummy rules
    rules_data = {
        "history": {
            "keep_threshold": 42
        }
    }
    with open(metadata_dir / ".qbrain-rules.yaml", "w", encoding="utf-8") as f:
        yaml.dump(rules_data, f)

    taint_data = {
        "labels": {
            "user_id": "USER_ID_OVERRIDE"
        }
    }
    with open(metadata_dir / ".qbrain-taint-labels.yaml", "w", encoding="utf-8") as f:
        yaml.dump(taint_data, f)

    # Create markdown rules
    with open(rules_dir / "vulnerabilities.md", "w", encoding="utf-8") as f:
        f.write("# Vulnerabilities Rule\n- Check SQL injection")

    # Mock Config
    config = Config()
    config.data["repo_path"] = str(tmp_path)
    config.data["vault_path"] = str(vault_dir)

    loader = RuleLoader(config)
    
    # Verify values
    rules = loader.load_rules_config()
    assert rules.get("history", {}).get("keep_threshold") == 42

    taints = loader.load_taint_labels()
    assert taints.get("user_id") == "USER_ID_OVERRIDE"

    markdown_rules = loader.load_markdown_rules()
    assert "vulnerabilities" in markdown_rules
    assert "Check SQL injection" in markdown_rules["vulnerabilities"]

    consolidated = loader.get_consolidated_rules_context()
    assert consolidated["config_rules"]["history"]["keep_threshold"] == 42
    assert consolidated["taint_labels"]["user_id"] == "USER_ID_OVERRIDE"
    assert "vulnerabilities" in consolidated["markdown_rules"]
