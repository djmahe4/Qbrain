import os
import json
import pytest
import subprocess
from brain.cli import get_cognitive_engine

@pytest.fixture
def auth_repo(tmp_path):
    repo_dir = os.path.join(tmp_path, "auth_repo")
    vault_dir = os.path.join(tmp_path, "vault")
    os.makedirs(repo_dir, exist_ok=True)
    os.makedirs(vault_dir, exist_ok=True)
    
    # 1. Initialize Git repository
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    
    # 2. Write authentication code
    src_dir = os.path.join(repo_dir, "src")
    os.makedirs(src_dir, exist_ok=True)
    app_file = os.path.join(src_dir, "auth.py")
    with open(app_file, "w", encoding="utf-8") as f:
        f.write(
            "def validate_password(password):\n"
            "    return len(password) >= 8\n"
            "\n"
            "def login_user(username, password):\n"
            "    \"\"\"\n"
            "    Authenticates user login credentials.\n"
            "    \"\"\"\n"
            "    if not validate_password(password):\n"
            "        raise ValueError('Invalid password format')\n"
            "    return True\n"
        )
        
    subprocess.run(["git", "add", "src/auth.py"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Add auth logic"], cwd=repo_dir, check=True)
    
    # 3. Create .quantum-brain.json configuration
    config_data = {
        "repo_path": repo_dir.replace("\\", "/"),
        "vault_path": vault_dir.replace("\\", "/"),
        "project_name": "test_auth_project"
    }
    with open(os.path.join(repo_dir, ".quantum-brain.json"), "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
        
    return repo_dir

def test_indexer_validation_pipeline(auth_repo, monkeypatch):
    monkeypatch.chdir(auth_repo)
    
    # Initialize Engine
    config, indexer, _, _, _, _, _, _, _ = get_cognitive_engine()
    
    # Index the repository
    res = indexer.index_repository(auth_repo)
    assert res.get("project") is not None
    
    # Diagnostic query to see all indexed functions
    all_funcs = indexer.query_graph("MATCH (f:Function) RETURN f.name AS name, labels(f) AS labels")
    print("\nDIAGNOSTIC ALL FUNCTIONS:", all_funcs)
    
    # Scenario 1: Find the Login Function
    funcs_res = indexer.search_graph(pattern="login", label="Function")
    print("DIAGNOSTIC SEARCH_GRAPH RESULTS:", funcs_res)
    funcs = funcs_res.get("results", funcs_res) if isinstance(funcs_res, dict) else funcs_res
    assert len(funcs) > 0
    login_func = funcs[0]
    assert login_func["name"] == "login_user"
    
    # Scenario 2: Verify Login Calls validate_password (Cypher Query)
    cypher = (
        "MATCH (login:Function {name: 'login_user'})-[:CALLS]->(validator:Function) "
        "RETURN validator.name AS name"
    )
    called_funcs = indexer.query_graph(cypher)
    assert any(f.get("name") == "validate_password" for f in called_funcs)
    
    # Scenario 3: Fetch Code Snippet by qualified_name
    q_name = login_func.get("qualified_name") or login_func.get("name")
    snippet_data = indexer.get_code_snippet(q_name)
    print("DIAGNOSTIC SNIPPET DATA:", snippet_data)
    assert "login_user" in snippet_data.get("source", "")
    assert "Authenticates user" in snippet_data.get("source", "")
    
    # Scenario 4: Trace Call Path (Outbound)
    path_trace = indexer.trace_path("login_user", direction="outbound", depth=2)
    print("DIAGNOSTIC PATH TRACE:", path_trace)
    assert "callees" in path_trace or "callers" in path_trace


