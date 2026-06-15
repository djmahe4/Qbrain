"""
Integration tests for the Indexer class.
Mocks subprocess.run to verify correct CLI tool invocation and response parsing.
"""
import json
import pytest
import subprocess
from unittest.mock import MagicMock, patch
from brain.indexer import Indexer
from brain.config import Config


def _make_indexer(tmp_path):
    config = Config()
    config.repo_path = str(tmp_path)
    return Indexer(config)

@pytest.fixture
def indexer(tmp_path):
    return _make_indexer(tmp_path)


# ─────────────────────────── CLI command construction ───────────────────────────

@patch("subprocess.run")
def test_run_cli_constructs_correct_command(mock_run, indexer):
    """_run_cli should build: [binary, 'cli', tool_name, json_args]"""
    mock_run.return_value = MagicMock(stdout="{}", returncode=0)
    
    indexer._run_cli("index_repository", {"repo_path": "/some/path"})
    
    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert cmd[1] == "cli"
    assert cmd[2] == "index_repository"
    args_dict = json.loads(cmd[3])
    assert args_dict["repo_path"] == "/some/path"


@patch("subprocess.run")
def test_run_cli_falls_back_when_which_returns_none(mock_run, indexer):
    """If shutil.which returns None, the raw binary name is used."""
    mock_run.return_value = MagicMock(stdout="{}", returncode=0)
    
    with patch("shutil.which", return_value=None):
        indexer._run_cli("list_projects", {})
    
    cmd = mock_run.call_args[0][0]
    assert "codebase-memory-mcp" in cmd[0]


@patch("subprocess.run")
def test_run_cli_raises_runtime_error_on_failure(mock_run, indexer):
    """CalledProcessError should be converted to RuntimeError."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd", stderr="Neo4j Error")
    
    with pytest.raises(RuntimeError) as exc:
        with patch("shutil.which", return_value="fake-bin"):
            indexer._run_cli("query_graph", {"query": "MATCH (n) RETURN n"})


@patch("subprocess.run")
def test_run_cli_raises_runtime_error_when_binary_missing(mock_run, indexer):
    """FileNotFoundError should be converted to RuntimeError."""
    mock_run.side_effect = FileNotFoundError()
    
    with pytest.raises(RuntimeError) as exc:
        with patch("shutil.which", return_value="fake-bin"):
            indexer._run_cli("index_repository", {"repo_path": "."})


# ─────────────────────────── index_repository ───────────────────────────

@patch("subprocess.run")
def test_index_repository_parses_json_response(mock_run, indexer):
    payload = {"status": "indexed", "files_processed": 42}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.index_repository("/mock/repo")
    
    assert result["status"] == "indexed"
    assert result["files_processed"] == 42


@patch("subprocess.run")
def test_index_repository_handles_non_json_response(mock_run, indexer):
    mock_run.return_value = MagicMock(stdout="Indexing complete!", returncode=0)
    
    result = indexer.index_repository("/mock/repo")
    
    assert "raw_result" in result
    assert result["raw_result"] == "Indexing complete!"


# ─────────────────────────── detect_changes ───────────────────────────

@patch("subprocess.run")
def test_detect_changes_returns_modified_files(mock_run, indexer):
    payload = {
        "modified_files": ["src/main.py"],
        "affected_symbols": ["main"]
    }
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.detect_changes()
    
    assert "src/main.py" in result["modified_files"]
    assert "affected_symbols" in result


@patch("subprocess.run")
def test_detect_changes_handles_empty_response(mock_run, indexer):
    payload = {"modified_files": [], "affected_symbols": []}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.detect_changes()
    
    assert result["modified_files"] == []


# ─────────────────────────── query_graph ───────────────────────────

@patch("subprocess.run")
def test_query_graph_with_list_response(mock_run, indexer):
    """query_graph should return the raw list when response is a JSON array."""
    payload = [{"name": "foo"}, {"name": "bar"}]
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.query_graph("MATCH (n) RETURN n")
    
    assert len(result) == 2
    assert result[0]["name"] == "foo"


@patch("subprocess.run")
def test_query_graph_with_dict_response(mock_run, indexer):
    """query_graph should return the dict when response is a JSON object (fallback)."""
    payload = {"results": [{"name": "foo"}]}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.query_graph("MATCH (n) RETURN n")
    
    assert result[0]["name"] == "foo"


@patch("subprocess.run")
def test_query_graph_with_language_field(mock_run, indexer):
    """Verify that the MCP response can include a 'language' field."""
    payload = [
        {"name": "func1", "language": "python"},
        {"name": "func2", "language": "typescript"}
    ]
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.query_graph("MATCH (f:Function) RETURN f.name, f.language")
    
    assert len(result) == 2
    assert result[0]["language"] == "python"
    assert result[1]["language"] == "typescript"


# ─────────────────────────── New Indexing & Querying Tools ───────────────────────────

@patch("subprocess.run")
def test_list_projects(mock_run, indexer):
    payload = {"projects": [{"name": "quant-blm", "nodes": 120, "edges": 450}]}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.list_projects()
    
    assert "projects" in result
    assert result["projects"][0]["name"] == "quant-blm"


@patch("subprocess.run")
def test_get_architecture(mock_run, indexer):
    payload = {"layers": ["api", "business"], "hotspots": ["main.cpp"]}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.get_architecture()
    
    assert "layers" in result
    assert "hotspots" in result


@patch("subprocess.run")
def test_trace_call_path(mock_run, indexer):
    payload = {"nodes": [{"name": "main"}], "edges": []}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.trace_call_path("main")
    
    assert "nodes" in result
    assert result["nodes"][0]["name"] == "main"


@patch("subprocess.run")
def test_get_code_snippet(mock_run, indexer):
    payload = {"code": "int main() { return 0; }", "file": "main.cpp"}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
    
    result = indexer.get_code_snippet("main")
    
    assert result["code"] == "int main() { return 0; }"
