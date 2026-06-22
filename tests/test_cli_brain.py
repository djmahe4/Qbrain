import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock, call
from brain.cli import app

runner = CliRunner()

@patch("brain.cli.get_cognitive_engine")
@patch("brain.slm.QBrainSLM")
@patch("brain.rag.retriever.VaultRetriever")
def test_brain_cli_command(mock_retriever, mock_slm, mock_get_cognitive, tmp_path):
    # Mock cognitive engine parts
    mock_config = MagicMock()
    mock_indexer = MagicMock()
    mock_embedder = MagicMock()
    mock_scorer = MagicMock()
    mock_store = MagicMock()
    mock_cem = MagicMock()
    mock_san = MagicMock()
    mock_cognitive = MagicMock()
    mock_api = MagicMock()
    
    mock_get_cognitive.return_value = (
        mock_config, mock_indexer, mock_embedder, mock_scorer,
        mock_store, mock_cem, mock_san, mock_cognitive, mock_api
    )
    
    # Mock SLM response
    mock_slm_instance = MagicMock()
    mock_slm_instance.generate.return_value = "Mocked SLM summary response"
    mock_slm.return_value = mock_slm_instance
    
    # Mock Retriever response
    mock_retriever_instance = MagicMock()
    mock_retriever_instance.retrieve.return_value = [{"file_path": "obsidian_vault/symbols/test.md", "content": "test symbol context"}]
    mock_retriever.return_value = mock_retriever_instance
    
    # 1. Test basic query
    result = runner.invoke(app, ["brain", "test_query"])
    assert result.exit_code == 0
    assert "qbrain SLM Cognitive Summary" in result.stdout
    assert "Mocked SLM summary response" in result.stdout
    
    # 2. Test ADR action delegation
    mock_indexer.manage_adr.return_value = {"status": "updated"}
    result_adr = runner.invoke(app, ["brain", "dummy", "--adr", "update", "--adr-content", "new content"])
    assert result_adr.exit_code == 0
    assert "ADR Action Result" in result_adr.stdout
    
    # Assert call with update parameters occurred
    assert call(action="update", adr_id=None, title=None, status=None, content="new content") in mock_indexer.manage_adr.mock_calls
