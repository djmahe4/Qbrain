import os
import pytest
import subprocess
from brain.sync_guard import SyncGuard, DriftEvent
from brain.config import Config
from brain.indexer import Indexer

@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = os.path.join(tmp_path, "repo")
    os.makedirs(repo_dir, exist_ok=True)
    return repo_dir

def test_sync_guard_tier3_reconciliation(temp_repo):
    guard = SyncGuard()
    
    # 1. Initialize git in temp_repo
    subprocess.run(["git", "init"], cwd=str(temp_repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(temp_repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(temp_repo), check=True)
    
    # Create src/old_app.py and commit it
    src_dir = os.path.join(temp_repo, "src")
    os.makedirs(src_dir, exist_ok=True)
    old_app = os.path.join(src_dir, "old_app.py")
    with open(old_app, "w") as f:
        f.write("def main():\n    pass\n")
        
    subprocess.run(["git", "add", "src/old_app.py"], cwd=str(temp_repo), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(temp_repo), check=True)
    
    # 2. Set up real indexer config and index
    config = Config()
    config.repo_path = str(temp_repo)
    config.data["vault_path"] = os.path.join(temp_repo, "obsidian_vault")
    config.data["cbm_binary"] = "codebase-memory-mcp"
    
    indexer = Indexer(config)
    res = indexer.index_repository(str(temp_repo))
    project_name = res.get("project")
    assert project_name is not None
    indexer.persistence.project_id = project_name
    
    # 3. Simulate file modifications:
    # Delete src/old_app.py from disk (becomes TOMBSTONE since it is in graph but missing on disk)
    os.remove(old_app)
    
    # Create src/new_helper.py (becomes UNINDEXED since it is on disk but missing in graph)
    new_helper = os.path.join(src_dir, "new_helper.py")
    with open(new_helper, "w") as f:
        f.write("def helper():\n    pass\n")
        
    # 4. Run Tier 3 reconciliation
    events = guard.run_tier3(str(temp_repo), indexer)
    
    # We expect:
    # TOMBSTONE: src/old_app.py (in graph, missing on disk)
    # UNINDEXED: src/new_helper.py (on disk, missing in graph)
    assert len(events) == 2
    types = {e.event_type for e in events}
    assert "TOMBSTONE" in types
    assert "UNINDEXED" in types
    
    tombstone_event = next(e for e in events if e.event_type == "TOMBSTONE")
    assert tombstone_event.file_path == "src/old_app.py"
    assert tombstone_event.severity == "WARN"
    
    unindexed_event = next(e for e in events if e.event_type == "UNINDEXED")
    assert unindexed_event.file_path == "src/new_helper.py"
    assert unindexed_event.severity == "INFO"

def test_should_trigger_repopulation():
    guard = SyncGuard()
    
    # Under 20% limit: 1 deleted file in 10 total -> False
    events_low = [
        DriftEvent(tier=2, event_type="DELETED", file_path="a.py", detail="", drift_seconds=0.0, severity="WARN")
    ]
    assert not guard.should_trigger_repopulation(events_low, total_files=10)
    
    # Over 20% limit: 2 deleted files in 5 total (40%) -> True
    events_high = [
        DriftEvent(tier=2, event_type="DELETED", file_path="a.py", detail="", drift_seconds=0.0, severity="WARN"),
        DriftEvent(tier=3, event_type="TOMBSTONE", file_path="b.py", detail="", drift_seconds=0.0, severity="WARN")
    ]
    assert guard.should_trigger_repopulation(events_high, total_files=5)
    
    # Critical merge-base divergence: REBASE_DETECTED present -> True
    events_rebase = [
        DriftEvent(tier=1, event_type="REBASE_DETECTED", file_path="", detail="", drift_seconds=0.0, severity="CRITICAL")
    ]
    assert guard.should_trigger_repopulation(events_rebase, total_files=100)
