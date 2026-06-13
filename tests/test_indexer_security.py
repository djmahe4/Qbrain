import pytest
import os
from brain.indexer import Indexer
from brain.config import Config

class MockConfig:
    def __init__(self, binary):
        self.cbm_binary = binary

def test_indexer_security_unauthorized_binary():
    config = MockConfig("malicious_tool")
    indexer = Indexer(config)
    
    with pytest.raises(RuntimeError) as excinfo:
        indexer._run_cli("test", {})
    
    assert "Security Risk" in str(excinfo.value)
    assert "malicious_tool" in str(excinfo.value)

def test_indexer_security_authorized_binary():
    # We use a real-ish name but it will fail later because it doesn't exist
    # but it should pass the initial security check
    config = MockConfig("codebase-memory-mcp")
    indexer = Indexer(config)
    
    # We expect FileNotFoundError or RuntimeError from subprocess, 
    # but NOT the "Security Risk" one.
    with pytest.raises(RuntimeError) as excinfo:
        indexer._run_cli("test", {})
    
    assert "Security Risk" not in str(excinfo.value)

def test_indexer_security_override():
    os.environ["QBRAIN_ALLOW_UNSAFE_BINARY"] = "1"
    try:
        config = MockConfig("any_binary")
        indexer = Indexer(config)
        
        with pytest.raises(RuntimeError) as excinfo:
            indexer._run_cli("test", {})
        
        assert "Security Risk" not in str(excinfo.value)
    finally:
        del os.environ["QBRAIN_ALLOW_UNSAFE_BINARY"]
