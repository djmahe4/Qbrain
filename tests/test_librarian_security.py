import pytest
import os
import shutil
import tempfile
from brain.librarian import LibrarianEngine

def test_librarian_safe_path_success():
    with tempfile.TemporaryDirectory() as tmp_vault:
        vault_path = os.path.abspath(tmp_vault)
        engine = LibrarianEngine(".", vault_path)
        safe = engine._safe_path("symbols", "ok.md")
        assert safe.startswith(vault_path)
        assert "ok.md" in safe

def test_librarian_safe_path_traversal():
    with tempfile.TemporaryDirectory() as tmp_vault:
        vault_path = os.path.abspath(tmp_vault)
        engine = LibrarianEngine(".", vault_path)
        # Go way above the root
        with pytest.raises(ValueError) as excinfo:
            engine._safe_path("symbols", "../../../../../../../../../../../../../../../../../../../../../../../../../../../etc/passwd")
        assert "Security Risk" in str(excinfo.value)

def test_librarian_export_traversal_prevention():
    with tempfile.TemporaryDirectory() as tmp_vault:
        vault_path = os.path.abspath(tmp_vault)
        engine = LibrarianEngine(".", vault_path)
        # Try to export a symbol with a malicious name
        bad_symbol = {
            "name": "../../../../../../../../../../../../../../../../../../../../../../../../../../../etc/passwd",
            "language": "python",
            "file": "test.py"
        }
        with pytest.raises(ValueError):
            engine.export_symbol(bad_symbol)
