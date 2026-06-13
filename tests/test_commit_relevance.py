import pytest
from unittest.mock import MagicMock
from brain.config import Config
from brain.git_watcher import GitWatcher

def test_calculate_commit_relevance_score():
    config = Config()
    config.data["rules"] = {
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

    watcher = GitWatcher(config, MagicMock(), MagicMock(), MagicMock())
    
    # Test high relevance: includes security changes
    diff_data_security = {
        "files": ["src/auth.cpp", "package.json"],
        "modified_symbols": ["validateToken"],
        "has_security": True,
        "has_error": False
    }
    score_sec = watcher.calculate_relevance_score(diff_data_security)
    # security weight (10) + symbol change (3) = 13 >= threshold 10
    assert score_sec >= 13

    # Test ignored change: only .md file
    diff_data_ignored = {
        "files": ["docs/cli_docs.md"],
        "modified_symbols": [],
        "has_security": False,
        "has_error": False
    }
    score_ign = watcher.calculate_relevance_score(diff_data_ignored)
    assert score_ign == 0
