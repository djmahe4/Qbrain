"""
TDD: RED Phase tests for brain.git_watcher cron behavior.
Tests cron job registration, check_diff pipeline, state persistence, and LRU sync.
"""
import json
import os
import time
import pytest
from unittest.mock import MagicMock, patch, call
from brain.git_watcher import GitWatcher
from brain.config import Config


def _make_watcher(tmp_path=None):
    config = Config()
    config.data["repo_path"] = str(tmp_path) if tmp_path else "."
    config.data["cron"] = {
        "git_diff_check_interval_minutes": 5,
        "branch_lru_sync_interval_minutes": 15,
        "full_reindex_cron": "0 2 * * *"
    }

    indexer = MagicMock()
    indexer.detect_changes.return_value = {"modified_files": [], "affected_symbols": []}
    indexer.query_graph.return_value = []

    scorer = MagicMock()
    embedder = MagicMock()
    embedder.embed.return_value = __import__("numpy").array([0.1, 0.2, 0.3])

    watcher = GitWatcher(config, indexer, scorer, embedder)
    return watcher, config, indexer, scorer, embedder


# ─────────────────────────── State persistence ───────────────────────────

def test_get_last_processed_commit_returns_empty_when_no_state(tmp_path):
    watcher, *_ = _make_watcher(tmp_path)
    assert watcher.get_last_processed_commit() == ""


def test_save_and_reload_commit_hash(tmp_path):
    watcher, *_ = _make_watcher(tmp_path)
    watcher.save_last_processed_commit("abc123def456")
    assert watcher.get_last_processed_commit() == "abc123def456"


def test_save_commit_includes_timestamp(tmp_path):
    watcher, *_ = _make_watcher(tmp_path)
    before = time.time()
    watcher.save_last_processed_commit("deadbeef")
    after = time.time()

    state_file = watcher.state_file
    assert os.path.exists(state_file)
    with open(state_file) as f:
        data = json.load(f)
    assert before <= data["timestamp"] <= after


def test_get_last_commit_graceful_on_corrupt_file(tmp_path):
    watcher, *_ = _make_watcher(tmp_path)
    # Write corrupted JSON
    with open(watcher.state_file, "w") as f:
        f.write("not valid json {{{")
    # Should not raise — returns empty string
    result = watcher.get_last_processed_commit()
    assert result == ""


# ─────────────────────────── check_diff pipeline ───────────────────────────

def test_check_diff_calls_detect_changes(tmp_path):
    watcher, _, indexer, *_ = _make_watcher(tmp_path)
    watcher.check_diff()
    indexer.detect_changes.assert_called_once()


def test_check_diff_no_changes_skips_simulation(tmp_path):
    watcher, _, indexer, scorer, _ = _make_watcher(tmp_path)
    indexer.detect_changes.return_value = {"modified_files": [], "affected_symbols": []}
    watcher.check_diff()
    scorer.run_simulation.assert_not_called()


def test_check_diff_with_changes_runs_simulation(tmp_path):
    watcher, _, indexer, scorer, _ = _make_watcher(tmp_path)
    indexer.detect_changes.return_value = {
        "modified_files": ["src/api.ts"],
        "affected_symbols": [{"name": "handleRequest"}]
    }
    # Mock the query_graph to return some functions
    indexer.query_graph.return_value = [
        {"name": "handleRequest", "file": "src/api.ts", "docstring": "Handles requests."}
    ]
    watcher.check_diff()
    scorer.run_simulation.assert_called_once()


def test_check_diff_with_changes_writes_to_graph(tmp_path):
    watcher, _, indexer, scorer, _ = _make_watcher(tmp_path)
    indexer.detect_changes.return_value = {
        "modified_files": ["brain/indexer.py"],
        "affected_symbols": []
    }
    indexer.query_graph.return_value = [
        {"name": "index_repository", "file": "brain/indexer.py", "docstring": "Index the repo."}
    ]
    watcher.check_diff()
    scorer.write_physics_to_graph.assert_called_once()


def test_check_diff_saves_commit_hash_after_update(tmp_path):
    watcher, _, indexer, scorer, _ = _make_watcher(tmp_path)
    indexer.detect_changes.return_value = {
        "modified_files": ["main.py"],
        "affected_symbols": []
    }
    indexer.query_graph.return_value = [
        {"name": "main", "file": "main.py", "docstring": "Entry point."}
    ]

    with patch("subprocess.check_output", return_value="cafebabe\n"):
        watcher.check_diff()

    assert watcher.get_last_processed_commit() == "cafebabe"


def test_check_diff_does_not_crash_on_exception(tmp_path):
    """check_diff should catch all exceptions and not propagate them."""
    watcher, _, indexer, *_ = _make_watcher(tmp_path)
    indexer.detect_changes.side_effect = RuntimeError("MCP not available")
    # Should not raise
    watcher.check_diff()


# ─────────────────────────── Git binary resolution ───────────────────────────

def test_check_diff_uses_resolved_git_binary(tmp_path):
    """Git subprocess call must use absolute path via shutil.which."""
    watcher, _, indexer, scorer, _ = _make_watcher(tmp_path)
    indexer.detect_changes.return_value = {
        "modified_files": ["x.py"],
        "affected_symbols": []
    }
    indexer.query_graph.return_value = [
        {"name": "func", "file": "x.py", "docstring": "does stuff"}
    ]

    with patch("shutil.which", return_value="/usr/bin/git") as mock_which, \
         patch("subprocess.check_output", return_value="deadbeef\n"):
        watcher.check_diff()
        # shutil.which should be called with "git" at some point
        git_calls = [c for c in mock_which.call_args_list if c[0][0] == "git"]
        assert len(git_calls) >= 1


# ─────────────────────────── Cron job registration ───────────────────────────

def test_start_registers_git_diff_job(tmp_path):
    watcher, config, *_ = _make_watcher(tmp_path)
    config.data["cron"]["git_diff_check_interval_minutes"] = 7

    with patch.object(watcher.scheduler, "add_job") as mock_add_job, \
         patch.object(watcher.scheduler, "start", side_effect=KeyboardInterrupt), \
         patch.object(watcher, "check_diff"):
        try:
            watcher.start()
        except (KeyboardInterrupt, SystemExit):
            pass

    jobs = [c for c in mock_add_job.call_args_list]
    assert len(jobs) >= 1
    # Check the first job uses the correct interval
    first_job_kwargs = jobs[0][1]
    assert first_job_kwargs.get("minutes") == 7


def test_start_registers_branch_lru_sync_job(tmp_path):
    """branch_lru_sync_interval_minutes config should result in a second cron job."""
    watcher, config, *_ = _make_watcher(tmp_path)
    config.data["cron"]["branch_lru_sync_interval_minutes"] = 15

    with patch.object(watcher.scheduler, "add_job") as mock_add_job, \
         patch.object(watcher.scheduler, "start", side_effect=KeyboardInterrupt), \
         patch.object(watcher, "check_diff"):
        try:
            watcher.start()
        except (KeyboardInterrupt, SystemExit):
            pass

    assert mock_add_job.call_count >= 2, "Expected at least 2 cron jobs (git_diff + lru_sync)"


def test_start_triggers_initial_check(tmp_path):
    """start() should immediately call check_diff once before starting the scheduler."""
    watcher, *_ = _make_watcher(tmp_path)

    with patch.object(watcher, "check_diff") as mock_check, \
         patch.object(watcher.scheduler, "add_job"), \
         patch.object(watcher.scheduler, "start", side_effect=KeyboardInterrupt):
        try:
            watcher.start()
        except (KeyboardInterrupt, SystemExit):
            pass

    mock_check.assert_called()
