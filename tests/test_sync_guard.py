import os
import time
import pytest
import subprocess
from unittest.mock import MagicMock, patch
from brain.sync_guard import SyncGuard, DriftEvent
from brain.persistence_manager import PersistenceManager
from brain.config import Config
from brain.indexer import Indexer

@pytest.fixture
def mock_persistence():
    # Setup mock persistence manager
    pm = MagicMock(spec=PersistenceManager)
    pm.project_id = "test-project"
    return pm

def test_sync_guard_unborn_branch():
    guard = SyncGuard()
    
    # Mock subprocess.run to simulate an unborn branch / empty git repo
    with patch("subprocess.run") as mock_run:
        # git merge-base --is-ancestor returns non-zero for unborn branch
        mock_run.side_effect = subprocess.CalledProcessError(128, "git merge-base")
        
        events = guard.run_tier1("/fake/repo", "somecommit")
        assert len(events) == 1
        assert events[0].event_type == "REBASE_DETECTED"
        assert events[0].severity == "CRITICAL"

def test_sync_guard_git_diff_success():
    guard = SyncGuard()
    
    with patch("subprocess.run") as mock_run:
        def side_effect(cmd, **kwargs):
            if "merge-base" in cmd:
                # Ancestor check succeeds
                return MagicMock(returncode=0)
            elif "diff" in cmd:
                # Return list of modified/deleted/added files
                output = "M\tsrc/main.py\nD\tsrc/utils.py\nA\tsrc/core.py"
                return MagicMock(stdout=output, returncode=0)
            return MagicMock(stdout="", returncode=0)
            
        mock_run.side_effect = side_effect
        
        events = guard.run_tier1("/fake/repo", "somecommit")
        assert len(events) == 3
        types = [e.event_type for e in events]
        assert "MODIFIED" in types
        assert "DELETED" in types
        assert "NEW" in types
        
        # Check files
        files = {e.file_path for e in events}
        assert files == {"src/main.py", "src/utils.py", "src/core.py"}

def test_sync_guard_tier2_mtime(tmp_path, mock_persistence):
    guard = SyncGuard()
    
    # Create some dummy files in temp directory
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    
    file1 = os.path.join(src_dir, "main.py")
    file2 = os.path.join(src_dir, "utils.py")
    
    with open(file1, "w") as f:
        f.write("def main(): pass")
    with open(file2, "w") as f:
        f.write("def utils(): pass")
        
    stat1 = os.stat(file1)
    stat2 = os.stat(file2)
    
    # Mock persistence manifest load
    # Initially: main.py is unmodified, utils.py has changed size/mtime, and core.py was deleted
    mock_persistence.load_manifest.return_value = {
        "src/main.py": (stat1.st_mtime, stat1.st_size),
        "src/utils.py": (stat2.st_mtime - 100, stat2.st_size - 10),
        "src/core.py": (time.time(), 500)
    }
    
    events = guard.run_tier2(str(tmp_path), mock_persistence)
    
    # Should detect:
    # utils.py as MODIFIED
    # core.py as DELETED
    # No event for main.py (unmodified)
    assert len(events) == 2
    event_types = {e.event_type for e in events}
    assert "MODIFIED" in event_types
    assert "DELETED" in event_types
    
    # Check details
    modified_event = next(e for e in events if e.event_type == "MODIFIED")
    assert modified_event.file_path == "src/utils.py"
    
    deleted_event = next(e for e in events if e.event_type == "DELETED")
    assert deleted_event.file_path == "src/core.py"

def test_sync_guard_future_timestamps(tmp_path, mock_persistence):
    guard = SyncGuard()
    
    file_path = os.path.join(tmp_path, "skew.py")
    with open(file_path, "w") as f:
        f.write("# Skew test")
        
    # Set mtime to the future (clock skew)
    future_time = time.time() + 100000
    os.utime(file_path, (future_time, future_time))
    
    stat = os.stat(file_path)
    mock_persistence.load_manifest.return_value = {
        "skew.py": (time.time() - 10, stat.st_size)
    }
    
    events = guard.run_tier2(str(tmp_path), mock_persistence)
    # Modified file with future timestamp should be caught as MODIFIED without crash
    assert len(events) == 1
    assert events[0].event_type == "MODIFIED"

def test_sync_guard_tier2_performance(tmp_path, mock_persistence):
    guard = SyncGuard()
    
    # Simulate a manifest with 10,000 files
    manifest_data = {}
    for i in range(10000):
        manifest_data[f"src/file_{i}.py"] = (time.time(), 100)
        
    mock_persistence.load_manifest.return_value = manifest_data
    
    # Create 500 actual files on disk to simulate subset of them being modified
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    for i in range(500):
        fpath = os.path.join(src_dir, f"file_{i}.py")
        with open(fpath, "w") as f:
            f.write("A" * 120)  # modified size
            
    start_time = time.time()
    events = guard.run_tier2(str(tmp_path), mock_persistence)
    end_time = time.time()
    
    elapsed = end_time - start_time
    print(f"Tier 2 scan of 10k manifest files took {elapsed:.4f} seconds")
    assert elapsed < 1.5  # Must complete under 1.5s

def test_sync_guard_real_integration(tmp_path):
    """
    Integration test utilizing real codebase-memory-mcp.
    Initializes a git repository, commits a file, indexes it,
    and runs query_graph to verify graph node creation.
    """
    # 1. Initialize Git repo on disk
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True)
    
    # 2. Create python file and commit
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    app_file = os.path.join(src_dir, "app.py")
    with open(app_file, "w") as f:
        f.write("def calculate_power(base, exponent):\n    \"\"\"Compute base^exponent.\"\"\"\n    return base ** exponent\n")
        
    subprocess.run(["git", "add", "src/app.py"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(tmp_path), check=True)
    
    # Get HEAD commit hash
    git_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(tmp_path), capture_output=True, text=True, check=True
    ).stdout.strip()
    
    # 3. Setup indexer config
    config = Config()
    config.repo_path = str(tmp_path)
    config.data["vault_path"] = os.path.join(tmp_path, "obsidian_vault")
    config.data["cbm_binary"] = "codebase-memory-mcp"
    
    indexer = Indexer(config)
    
    # 4. Trigger indexing
    res = indexer.index_repository(str(tmp_path))
    project_name = res.get("project")
    assert project_name is not None
    
    # Re-align persistence project ID
    indexer.persistence.project_id = project_name
    
    # 5. Query the graph to verify node creation
    query = (
        "MATCH (f:Function) WHERE f.name = 'calculate_power' "
        "RETURN f.name AS name, f.docstring AS docstring"
    )
    records = indexer.query_graph(query)
    
    assert len(records) > 0
    assert records[0]["name"] == "calculate_power"
    
    # 6. Verify SyncGuard detects changes against this real project database
    guard = SyncGuard()
    
    # Run Tier 1 Git check
    drift_events = guard.run_tier1(str(tmp_path), git_head)
    assert len(drift_events) == 0  # No changes since the commit
    
    # Run Tier 2 Filesystem walk check (records baseline manifest snapshot)
    tier2_events = guard.run_tier2(str(tmp_path), indexer.persistence)
    # The manifest was empty, so all files on disk are detected as NEW on first run
    assert len(tier2_events) == 1
    assert tier2_events[0].event_type == "NEW"
    assert tier2_events[0].file_path == "src/app.py"
    
    # Run Tier 2 again - should detect no new/modified/deleted files since manifest is baseline
    tier2_events_subsequent = guard.run_tier2(str(tmp_path), indexer.persistence)
    assert len(tier2_events_subsequent) == 0

