import pytest
from unittest.mock import patch, MagicMock
from brain.indexer import Indexer
from brain.config import Config

@patch("subprocess.run")
def test_run_cli_eliminates_shell_true_success(mock_run):
    config = Config()
    indexer = Indexer(config)

    mock_response = MagicMock()
    mock_response.stdout = "{}"
    mock_run.return_value = mock_response

    indexer.query_graph("MATCH (n) RETURN n")

    assert mock_run.call_count == 1
    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("shell") is not True

@patch("subprocess.run")
def test_run_cli_eliminates_shell_true_failure(mock_run):
    config = Config()
    indexer = Indexer(config)

    import subprocess
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd", stderr="error")

    with pytest.raises(RuntimeError):
        indexer.query_graph("MATCH (n) RETURN n")

    assert mock_run.call_count == 1
    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("shell") is not True
