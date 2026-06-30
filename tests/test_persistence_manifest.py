import os
import sqlite3
import time
import json
import pytest
import threading
import subprocess
from unittest.mock import MagicMock, patch
from brain.persistence_manager import PersistenceManager
from brain.config import Config
from brain.indexer import Indexer
from brain.commands.library import sync_library

@pytest.fixture
def mock_indexer_isolated(tmp_path):
    import re
    repo = str(tmp_path)
    safe_name = re.sub(r"[^a-zA-Z0-9\-]", "-", repo)
    safe_name = re.sub(r"-+", "-", safe_name)
    project_name = safe_name.strip("-")
    
    indexer = MagicMock()
    indexer._get_project_name.return_value = project_name
    return indexer

@pytest.fixture
def db_path(tmp_path):
    return os.path.join(tmp_path, "qbrain-mind-test.sqlite")

def test_manifest_crud(db_path, mock_indexer_isolated):
    # Initialize PM (which should create tables)
    pm = PersistenceManager(db_path, mock_indexer_isolated)
    
    # Save a baseline manifest snapshot
    files_snapshot = {
        "src/main.py": (1624364000.0, 1024),
        "src/utils.py": (1624364005.0, 2048),
        "src/core.py": (1624364010.0, 4096),
    }
    pm.save_manifest_snapshot(files_snapshot)
    
    # Load manifest and verify
    manifest = pm.load_manifest()
    assert len(manifest) == 3
    assert manifest["src/main.py"] == (1624364000.0, 1024)
    assert manifest["src/utils.py"] == (1624364005.0, 2048)
    
    # Update a file in the snapshot
    updated_snapshot = {
        "src/main.py": (1624364900.0, 1050),
        "src/utils.py": (1624364005.0, 2048),
    }
    pm.save_manifest_snapshot(updated_snapshot)
    
    manifest = pm.load_manifest()
    assert manifest["src/main.py"] == (1624364900.0, 1050)
    assert "src/core.py" in manifest

def test_tombstones(db_path, mock_indexer_isolated):
    pm = PersistenceManager(db_path, mock_indexer_isolated)
    
    files_snapshot = {
        "src/main.py": (1624364000.0, 1024),
        "src/utils.py": (1624364005.0, 2048),
    }
    pm.save_manifest_snapshot(files_snapshot)
    
    assert len(pm.get_tombstones()) == 0
    
    pm.mark_tombstone("src/main.py")
    tombstones = pm.get_tombstones()
    assert tombstones == ["src/main.py"]
    
    # Test idempotency
    pm.mark_tombstone("src/main.py")
    assert pm.get_tombstones() == ["src/main.py"]
    
    # Non-existent file
    pm.mark_tombstone("src/unknown.py")
    assert set(pm.get_tombstones()) == {"src/main.py", "src/unknown.py"}

def test_symbol_confidence(db_path, mock_indexer_isolated):
    pm = PersistenceManager(db_path, mock_indexer_isolated)
    
    assert pm.get_symbol_confidence("calculate_sum") is None
    
    pm.save_symbol_confidence("calculate_sum", 0.75, "full")
    assert pm.get_symbol_confidence("calculate_sum") == 0.75
    
    pm.save_symbol_confidence("calculate_sum", 0.42, "stub")
    assert pm.get_symbol_confidence("calculate_sum") == 0.42

def test_manifest_scale_performance(db_path, mock_indexer_isolated):
    pm = PersistenceManager(db_path, mock_indexer_isolated)
    
    large_snapshot = {
        f"src/file_{i}.py": (1624364000.0 + i, 1000 + i)
        for i in range(50000)
    }
    
    start_time = time.time()
    pm.save_manifest_snapshot(large_snapshot)
    end_time = time.time()
    
    elapsed = end_time - start_time
    assert elapsed < 2.0  # Under 2 seconds

def test_manifest_concurrency(db_path, mock_indexer_isolated):
    pm = PersistenceManager(db_path, mock_indexer_isolated)
    
    errors = []
    
    def worker(worker_id):
        try:
            snapshot = {f"src/worker_{worker_id}_file_{i}.py": (time.time(), i) for i in range(100)}
            pm.save_manifest_snapshot(snapshot)
        except Exception as e:
            errors.append(e)
            
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    assert len(errors) == 0

def test_sync_library_loop_simulation(tmp_path):
    """
    Simulate the qbrain sync loop using the real codebase-memory-mcp CLI execution
    and verifying the integration with PersistenceManager's new tables/methods.
    """
    # Create configuration
    config = Config()
    config.repo_path = str(tmp_path)
    config.data["vault_path"] = os.path.join(tmp_path, "obsidian_vault")
    config.data["cbm_binary"] = "codebase-memory-mcp"
    
    # Create a dummy python file with a function to be indexed
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    dummy_file = os.path.join(src_dir, "app.py")
    with open(dummy_file, "w") as f:
        f.write("def main():\n    \"\"\"This is the main entry point.\"\"\"\n    print('Hello World')\n")
        
    # Set up indexer
    indexer = Indexer(config)
    
    # Run the real index_repository first to populate the graph db
    indexer.index_repository(str(tmp_path))
    indexer.persistence.project_id = indexer._get_project_name()
    
    # Save a baseline belief in SQLite to test PM merging during sync
    # We qualify the name with 'src/app.py:' since that's how the indexer identifies functions
    indexer.persistence.persist_belief("src/app.py:main", {
        "beliefs": {"Gate": 0.8},
        "status": "ACTIVE",
        "winner": "Gate",
        "support_mass": 1.5,
        "potential_energy": 0.2
    })
    
    # Simulate first qbrain sync
    console_mock = MagicMock()
    sync_library(config, indexer, console_mock)
    
    # Verify tables are initialized and load_manifest can run
    manifest = indexer.persistence.load_manifest()
    assert isinstance(manifest, dict)

    # Validate SQLite persistence data
    conn = sqlite3.connect(indexer.persistence.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, winner, support_mass FROM beliefs WHERE symbol = ?", ("src/app.py:main",))
    row = cursor.fetchone()
    assert row is not None
    assert row[1] == "Gate"
    assert row[2] == 1.5
    conn.close()

    # Validate Obsidian Vault data
    vault_path = config.data["vault_path"]
    assert os.path.exists(vault_path)

    # Confirm files directory exists and contains markdown reports
    files_dir = os.path.join(vault_path, "files")
    assert os.path.exists(files_dir)

    file_files = os.listdir(files_dir)
    assert len(file_files) > 0

    # Ensure files contain valid frontmatter and metadata
    file_path = os.path.join(files_dir, "src_app_py.md")
    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as sf:
        content = sf.read()
        assert content.startswith("---")
        assert "type: file" in content
        assert "### Symbol: main" in content

