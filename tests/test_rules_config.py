import pytest
import os
import yaml
from brain.config import Config

def test_config_rules_defaults():
    config = Config()
    # It should load default weights and threshold
    assert hasattr(config, "rules") or "rules" in config.data
    rules = config.data.get("rules", {})
    assert rules.get("history", {}).get("keep_threshold") is not None
    assert rules.get("history", {}).get("weights") is not None

def test_config_rules_merge_overrides(tmp_path):
    # Setup custom override .qbrain-rules.yaml
    rules_data = {
        "history": {
            "keep_threshold": 12,
            "weights": {
                "security_change": 15
            }
        }
    }
    rules_file = tmp_path / ".qbrain-rules.yaml"
    rules_file.write_text(yaml.dump(rules_data))

    config = Config()
    # Mock repo_path to check override behavior
    config.data["repo_path"] = str(tmp_path)
    config._load_rules_config()

    # Threshold should override
    assert config.data["rules"]["history"]["keep_threshold"] == 12
    # Security weight should override
    assert config.data["rules"]["history"]["weights"]["security_change"] == 15
    # Other weights should fallback to defaults
    assert "symbol_change" in config.data["rules"]["history"]["weights"]
