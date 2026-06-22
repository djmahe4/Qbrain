import os
import json
import pytest
import subprocess
from typer.testing import CliRunner
from brain.cli import app, get_cognitive_engine
from brain.commands.library import sync_library
from rich.console import Console

runner = CliRunner()

@pytest.fixture
def temp_repo(tmp_path):
    repo_dir = os.path.join(tmp_path, "repo")
    vault_dir = os.path.join(tmp_path, "vault")
    os.makedirs(repo_dir, exist_ok=True)
    os.makedirs(vault_dir, exist_ok=True)
    return repo_dir, vault_dir

def test_brain_cli_command_real_simulation(temp_repo, monkeypatch):
    repo_dir, vault_dir = temp_repo
    
    # 1. Initialize git in temp_repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    
    # Create a source file with docstring
    src_dir = os.path.join(repo_dir, "src")
    os.makedirs(src_dir, exist_ok=True)
    app_file = os.path.join(src_dir, "app.py")
    with open(app_file, "w", encoding="utf-8") as f:
        f.write(
            "def login_user(username, password):\n"
            "    \"\"\"\n"
            "    Authenticates user login credentials.\n"
            "    \"\"\"\n"
            "    if len(password) < 8:\n"
            "        raise ValueError('Password too short')\n"
            "    return True\n"
        )
        
    subprocess.run(["git", "add", "src/app.py"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True)
    
    # Write .quantum-brain.json configuration to temp repo directory
    config_data = {
        "repo_path": repo_dir.replace("\\", "/"),
        "vault_path": vault_dir.replace("\\", "/"),
        "correlation_threshold": 0.3
    }
    config_file = os.path.join(repo_dir, ".quantum-brain.json")
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
        
    # Change directory to the temp repository so that the CLI get_engine loads our local config file
    monkeypatch.chdir(repo_dir)
    
    # 2. Get real engines using get_cognitive_engine
    config, indexer, embedder, scorer, store, cem, san, cognitive, api = get_cognitive_engine()
    
    res = indexer.index_repository(repo_dir)
    project_name = res.get("project")
    assert project_name is not None
    
    # 3. Synchronize library/vault first so notes and sqlite databases are populated
    sync_library(config, indexer, Console())

    # Run score pass to write simulation values/beliefs to database
    from brain.commands.monitor import score_graph
    score_graph(15, config, indexer, embedder, scorer, Console())

    # 4. Invoke CLI "brain" command with correlate active (no mocks used)
    result = runner.invoke(app, ["brain", "login_user", "--correlate"])
    assert result.exit_code == 0
    assert "qbrain SLM Cognitive Summary" in result.stdout
    assert "Semantic Correlations" in result.stdout
    assert "src/app.py:login_user" in result.stdout

    # 5. Test ADR action delegation is preserved
    result_adr = runner.invoke(app, ["brain", "dummy", "--adr", "update", "--adr-content", "new content"])
    assert result_adr.exit_code == 0
    assert "ADR Action Result" in result_adr.stdout
