"""
TDD: RED Phase integration tests for brain.indexer (Indexer + codebase-memory-mcp)
Uses subprocess mocking to verify CLI command construction, response parsing,
and edge-case handling without requiring actual codebase-memory-mcp installed.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from brain.indexer import Indexer
from brain.config import Config


def _make_indexer():
    config = Config()
    config.data["cbm_binary"] = "codebase-memory-mcp"
    config.data["repo_path"] = "."
    return Indexer(config)


# ─────────────────────────── CLI command construction ───────────────────────────

@patch("subprocess.run")
def test_run_cli_constructs_correct_command(mock_run):
    """_run_cli should build: [binary, 'cli', tool_name, json_args]"""
    mock_run.return_value = MagicMock(stdout='{"ok": true}', returncode=0)

    with patch("shutil.which", return_value="/usr/local/bin/codebase-memory-mcp"):
        indexer = _make_indexer()
        indexer._run_cli("index_repository", {"repo_path": "/some/path"})

    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/usr/local/bin/codebase-memory-mcp"
    assert cmd[1] == "cli"
    assert cmd[2] == "index_repository"
    args_dict = json.loads(cmd[3])
    assert args_dict["repo_path"] == "/some/path"


@patch("subprocess.run")
def test_run_cli_falls_back_when_which_returns_none(mock_run):
    """If shutil.which returns None, the raw binary name is used."""
    mock_run.return_value = MagicMock(stdout='{}', returncode=0)

    with patch("shutil.which", return_value=None):
        indexer = _make_indexer()
        indexer._run_cli("detect_changes", {"repo_path": "."})

    cmd = mock_run.call_args[0][0]
    # Falls back to raw name
    assert "codebase-memory-mcp" in cmd[0]


@patch("subprocess.run")
def test_run_cli_raises_runtime_error_on_failure(mock_run):
    """CalledProcessError should be converted to RuntimeError."""
    import subprocess
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd", stderr="Not found")

    with patch("shutil.which", return_value=None):
        indexer = _make_indexer()
        with pytest.raises(RuntimeError, match="codebase-memory-mcp"):
            indexer._run_cli("query_graph", {"query": "MATCH (n) RETURN n"})


@patch("subprocess.run")
def test_run_cli_raises_runtime_error_when_binary_missing(mock_run):
    """FileNotFoundError should be converted to RuntimeError."""
    mock_run.side_effect = FileNotFoundError("binary not found")

    with patch("shutil.which", return_value=None):
        indexer = _make_indexer()
        with pytest.raises(RuntimeError, match="Could not find"):
            indexer._run_cli("index_repository", {"repo_path": "."})


# ─────────────────────────── index_repository ───────────────────────────

@patch("subprocess.run")
def test_index_repository_parses_json_response(mock_run):
    payload = {"status": "indexed", "files_processed": 42}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.index_repository("/some/path")

    assert result["status"] == "indexed"
    assert result["files_processed"] == 42


@patch("subprocess.run")
def test_index_repository_handles_non_json_response(mock_run):
    mock_run.return_value = MagicMock(stdout="Indexing complete!", returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.index_repository()

    assert "raw_result" in result
    assert result["raw_result"] == "Indexing complete!"


# ─────────────────────────── detect_changes ───────────────────────────

@patch("subprocess.run")
def test_detect_changes_returns_modified_files(mock_run):
    payload = {
        "modified_files": ["src/api.ts", "brain/indexer.py"],
        "affected_symbols": [{"name": "handleRequest"}, {"name": "index_repository"}]
    }
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.detect_changes()

    assert "modified_files" in result
    assert len(result["modified_files"]) == 2
    assert "affected_symbols" in result


@patch("subprocess.run")
def test_detect_changes_handles_empty_response(mock_run):
    payload = {"modified_files": [], "affected_symbols": []}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.detect_changes()

    assert result["modified_files"] == []


# ─────────────────────────── query_graph ───────────────────────────

@patch("subprocess.run")
def test_query_graph_with_list_response(mock_run):
    """query_graph should return the raw list when response is a JSON array."""
    records = [{"name": "foo", "docstring": "bar"}, {"name": "baz", "docstring": "qux"}]
    mock_run.return_value = MagicMock(stdout=json.dumps(records), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.query_graph("MATCH (f:Function) RETURN f")

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "foo"


@patch("subprocess.run")
def test_query_graph_with_dict_response(mock_run):
    """query_graph should return the dict when response is a JSON object."""
    payload = {"results": [{"name": "myFunc"}], "total": 1}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.query_graph("MATCH (f:Function) RETURN f")

    assert isinstance(result, dict)
    assert "results" in result


@patch("subprocess.run")
def test_query_graph_with_language_field(mock_run):
    """Verify that the MCP response can include a 'language' field."""
    records = [
        {"name": "transferOwnership", "file": "contracts/Ownable.sol", "language": "solidity", "docstring": "Transfers ownership."},
        {"name": "fetchData", "file": "src/api.ts", "language": "typescript", "docstring": "Fetches remote data."},
    ]
    mock_run.return_value = MagicMock(stdout=json.dumps(records), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.query_graph("MATCH (f:Function) RETURN f.name, f.language, f.docstring, f.file")

    assert result[0]["language"] == "solidity"
    assert result[1]["language"] == "typescript"


# ─────────────────────────── New Indexing & Querying Tools ───────────────────────────

@patch("subprocess.run")
def test_list_projects(mock_run):
    payload = {"projects": [{"name": "quant-blm", "nodes": 120, "edges": 450}]}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.list_projects()

    assert "projects" in result
    assert result["projects"][0]["name"] == "quant-blm"


@patch("subprocess.run")
def test_get_architecture(mock_run):
    payload = {"layers": ["api", "business"], "hotspots": ["main.cpp"]}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.get_architecture("quant-blm")

    assert "layers" in result
    assert "hotspots" in result


@patch("subprocess.run")
def test_trace_call_path(mock_run):
    payload = {"nodes": [{"name": "main"}], "edges": []}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.trace_call_path("main", direction="both", project="quant-blm")

    assert "nodes" in result
    assert result["nodes"][0]["name"] == "main"


@patch("subprocess.run")
def test_get_code_snippet(mock_run):
    payload = {"source": "int main() { return 0; }", "file": "main.cpp"}
    mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)

    with patch("shutil.which", return_value="/usr/bin/cbm"):
        indexer = _make_indexer()
        result = indexer.get_code_snippet("main", project="quant-blm", context_lines=5)

    assert result["source"] == "int main() { return 0; }"

