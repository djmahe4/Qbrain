import pytest
import os
import tempfile
from brain.indexer import Indexer
from brain.config import Config

class MockConfig:
    def __init__(self, binary, repo_path):
        self.cbm_binary = binary
        self.repo_path = repo_path

@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp

def test_indexer_security_unauthorized_binary(temp_repo):
    config = MockConfig("malicious_tool", temp_repo)
    indexer = Indexer(config)
    
    with pytest.raises(RuntimeError) as excinfo:
        indexer._run_cli("test", {})
    
    assert "Security Risk" in str(excinfo.value)
    assert "malicious_tool" in str(excinfo.value)

def test_indexer_security_authorized_binary(temp_repo):
    # codebase-memory-mcp is authorized
    config = MockConfig("codebase-memory-mcp", temp_repo)
    indexer = Indexer(config)
    
    # We expect RuntimeError from subprocess failure (not found), 
    # but NOT the "Security Risk" one.
    with pytest.raises(RuntimeError) as excinfo:
        indexer._run_cli("test", {})
    
    assert "Security Risk" not in str(excinfo.value)

def test_indexer_security_override(temp_repo):
    os.environ["QBRAIN_ALLOW_UNSAFE_BINARY"] = "1"
    try:
        config = MockConfig("any_binary", temp_repo)
        indexer = Indexer(config)
        
        # Should not raise "Security Risk" due to environment override
        with pytest.raises(RuntimeError) as excinfo:
            indexer._run_cli("test", {})
        
        assert "Security Risk" not in str(excinfo.value)
    finally:
        del os.environ["QBRAIN_ALLOW_UNSAFE_BINARY"]
