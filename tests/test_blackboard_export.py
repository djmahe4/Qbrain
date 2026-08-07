import os
import shutil
import pytest
from brain.librarian import LibrarianEngine
from brain.sync_guard import DriftEvent
from brain.config import Config
from brain.indexer import Indexer

@pytest.fixture
def temp_vault(tmp_path):
    vault_dir = os.path.join(tmp_path, "vault")
    repo_dir = os.path.join(tmp_path, "repo")
    os.makedirs(vault_dir, exist_ok=True)
    os.makedirs(repo_dir, exist_ok=True)
    return repo_dir, vault_dir

@pytest.fixture
def real_indexer(temp_vault):
    repo_dir, vault_dir = temp_vault
    config = Config()
    config.repo_path = repo_dir
    config.data["vault_path"] = vault_dir
    config.data["cbm_binary"] = "codebase-memory-mcp"
    return Indexer(config)

def test_blackboard_directory_setup(temp_vault, real_indexer):
    repo_dir, vault_dir = temp_vault
    engine = LibrarianEngine(repo_dir, vault_dir, indexer=real_indexer)
    engine.setup_vault()
    
    # Confirm blackboard directory is created
    assert os.path.exists(os.path.join(vault_dir, "blackboard"))

def test_export_blackboard_note(temp_vault, real_indexer):
    repo_dir, vault_dir = temp_vault
    engine = LibrarianEngine(repo_dir, vault_dir, indexer=real_indexer)
    engine.setup_vault()
    
    drift_events = [
        DriftEvent(
            tier=2,
            event_type="MODIFIED",
            file_path="src/app.py",
            detail="Modified size",
            drift_seconds=10.5,
            severity="INFO"
        ),
        DriftEvent(
            tier=2,
            event_type="DELETED",
            file_path="src/utils.py",
            detail="File deleted from disk",
            drift_seconds=0.0,
            severity="WARN"
        )
    ]
    
    # Export note
    engine.export_blackboard_note(drift_events)
    
    blackboard_dir = os.path.join(vault_dir, "blackboard")
    notes = os.listdir(blackboard_dir)
    assert len(notes) == 1
    assert notes[0].endswith(".md")
    
    note_path = os.path.join(blackboard_dir, notes[0])
    with open(note_path, "r", encoding="utf-8") as f:
        content = f.read()
        # Verify YAML frontmatter elements
        assert "type: blackboard" in content
        assert "event_count: 2" in content
        assert "severity_max: WARN" in content
        assert "tier_max: 2" in content
        # Verify headings
        assert "## 📡 Drift Events" in content
        assert "src/app.py" in content
        assert "src/utils.py" in content

def test_prune_stale_pages(temp_vault, real_indexer):
    repo_dir, vault_dir = temp_vault
    engine = LibrarianEngine(repo_dir, vault_dir, indexer=real_indexer)
    engine.setup_vault()
    
    # Create test pages in symbols, files, behaviors, changes, and blackboard
    symbols_dir = os.path.join(vault_dir, "symbols")
    files_dir = os.path.join(vault_dir, "files")
    behaviors_dir = os.path.join(vault_dir, "behaviors")
    changes_dir = os.path.join(vault_dir, "changes")
    blackboard_dir = os.path.join(vault_dir, "blackboard")
    
    # Write mock pages with real-matching keys in YAML
    symbol_page = os.path.join(symbols_dir, "calculate_power.md")
    with open(symbol_page, "w", encoding="utf-8") as f:
        f.write("---\ntype: symbol\nfile: src/app.py\n---\n# calculate_power")
        
    file_page = os.path.join(files_dir, "src_app_py.md")
    with open(file_page, "w", encoding="utf-8") as f:
        f.write("---\ntype: file\nfile_path: src/app.py\n---\n# app.py")
        
    behavior_page = os.path.join(behaviors_dir, "app_behavior.md")
    with open(behavior_page, "w", encoding="utf-8") as f:
        f.write("---\ntype: behavior\nentrypoint: src/app.py:main\n---\n# app_behavior")
        
    # Page from a non-deleted file
    other_symbol_page = os.path.join(symbols_dir, "keep_me.md")
    with open(other_symbol_page, "w", encoding="utf-8") as f:
        f.write("---\ntype: symbol\nfile: src/core.py\n---\n# keep_me")
        
    # Changes and blackboard files (which should NEVER be deleted)
    change_page = os.path.join(changes_dir, "recent.md")
    with open(change_page, "w", encoding="utf-8") as f:
        f.write("---\ntype: change\nfile: src/app.py\n---\n# change")
        
    bb_page = os.path.join(blackboard_dir, "note.md")
    with open(bb_page, "w", encoding="utf-8") as f:
        f.write("---\ntype: blackboard\nfile: src/app.py\n---\n# bb note")
        
    # Prune stale pages for tombstoned files (src/app.py is tombstoned)
    engine.prune_stale_pages(["src/app.py"])
    
    # Assert src/app.py related pages are deleted
    assert not os.path.exists(symbol_page)
    assert not os.path.exists(file_page)
    assert not os.path.exists(behavior_page)
    
    # Assert other pages are kept
    assert os.path.exists(other_symbol_page)
    assert os.path.exists(change_page)
    assert os.path.exists(bb_page)
