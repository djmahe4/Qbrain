import pytest
from unittest.mock import patch, MagicMock
from brain.indexer import Indexer
from brain.config import Config

@patch("subprocess.run")
def test_manage_adr_maps_mode(mock_run):
    config = Config()
    indexer = Indexer(config)

    mock_response = MagicMock()
    mock_response.stdout = '{"status": "updated"}'
    mock_run.return_value = mock_response

    # Test "create" action maps to "update" mode
    res = indexer.manage_adr(action="create", content="## PURPOSE\nTest content")
    assert res == {"status": "updated"}
    assert mock_run.call_count == 1
    
    # Assert args passed to CLI
    args = mock_run.call_args[0][0]
    import json
    payload = json.loads(args[-1])
    assert payload["mode"] == "update"
    assert payload["action"] == "create"
    assert payload["content"] == "## PURPOSE\nTest content"
