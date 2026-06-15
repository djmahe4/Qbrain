import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from brain.cli import app

runner = CliRunner()

@patch("brain.entrypoint_finder.EntrypointFinder.find_entrypoints")
@patch("brain.cli.Config")
def test_entrypoints_cli_command(mock_config, mock_find_entrypoints, tmp_path):
    mock_config_instance = MagicMock()
    mock_config_instance.repo_path = str(tmp_path)
    mock_config.return_value = mock_config_instance
    
    mock_find_entrypoints.return_value = [
        {"name": "main", "type": "package.json", "file": "src/index.js"},
        {"name": "my-cli", "type": "package.json", "file": "bin/cli.js"}
    ]
    
    result = runner.invoke(app, ["entrypoints"])
    
    assert result.exit_code == 0
    assert "Codebase Entrypoints" in result.stdout
    assert "src/index.js" in result.stdout
    assert "package.json" in result.stdout
