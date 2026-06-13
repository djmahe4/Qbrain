import pytest
import sys
import tempfile
import os
from brain.config import Config

def test_config_invalid_json_outputs_warning(capsys):
    # Create a temporary malformed config file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        tmp.write("{ malformed json }")
        tmp_name = tmp.name

    try:
        # Load config pointing to this temporary file
        cfg = Config(config_path=tmp_name)
        
        # Verify stderr contains JSON syntax error warning
        captured = capsys.readouterr()
        assert "Warning: Failed to parse configuration file" in captured.err
        assert "json.decoder.JSONDecodeError" in captured.err or "Expecting property name" in captured.err

        # Check that it safely fell back to default configuration values
        assert cfg.lru_maxsize == 512
    finally:
        # Clean up temp file
        os.remove(tmp_name)
