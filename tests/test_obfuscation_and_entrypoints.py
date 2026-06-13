import pytest
import os
import tempfile
import json
from brain.entrypoint_finder import EntrypointFinder
from brain.language_parser import LanguageParser

def test_hidden_php_entrypoint():
    with tempfile.TemporaryDirectory() as tmp_repo:
        # Create a deep unexpected folder
        deep_folder = os.path.join(tmp_repo, "src", "assets", "vendor", "legacy", "bootstrap")
        os.makedirs(deep_folder)
        
        # Hide a PHP entrypoint there
        php_file = os.path.join(deep_folder, "index.php")
        with open(php_file, "w") as f:
            f.write("<?php echo 'Hidden Entrypoint'; ?>")
            
        finder = EntrypointFinder(tmp_repo)
        entrypoints = finder.find_entrypoints()
        
        # Verify it found the hidden PHP file
        found_files = [e["file"] for e in entrypoints]
        assert "src/assets/vendor/legacy/bootstrap/index.php" in found_files

def test_highly_hidden_php_entrypoint():
    with tempfile.TemporaryDirectory() as tmp_repo:
        # Hide a PHP file with a non-standard name deep in a vendor folder
        hidden_path = os.path.join(tmp_repo, "vendor", "logic", "bootstrap", "core_init.php")
        os.makedirs(os.path.dirname(hidden_path))
        with open(hidden_path, "w") as f:
            # Content that looks like an entrypoint (lots of includes/requires)
            f.write("<?php require_once 'config.php'; require 'db.php'; include 'router.php'; ?>")
            
        finder = EntrypointFinder(tmp_repo)
        entrypoints = finder.find_entrypoints()
        
        found_files = [e["file"] for e in entrypoints]
        # This should fail with current implementation
        assert any("core_init.php" in f for f in found_files)

def test_obfuscation_robustness_harmful_content():
    parser = LanguageParser()
    # Code with 'HARMFULL CONTENT' alias and real security risk
    code = """
    # This is a safe comment
    HARMFULL CONTENT = "This is a decoy"
    def process_data(user_input):
        eval(user_input) # Real risk
    """
    warnings = parser.parse_coding_standards({
        "name": "process_data", 
        "code_snippet": code,
        "signature": "def process_data(user_input)",
        "file": "utils.py"
    })
    
    # Should still detect the eval risk despite the 'HARMFULL CONTENT' decoy
    assert any("Security critical" in w for w in warnings)

def test_obfuscation_robustness_binary_strings():
    parser = LanguageParser()
    # Random binary-looking strings to confuse AI
    binary_junk = "\\x01\\xff\\xfe\\x00\\xde\\xad\\xbe\\xef" * 10
    code = f"""
    def secure_op(token):
        # {binary_junk}
        # {binary_junk}
        requests.get("https://api.com/data") # Risk: missing timeout
    """
    warnings = parser.parse_coding_standards({
        "name": "secure_op", 
        "code_snippet": code,
        "signature": "def secure_op(token)",
        "file": "ops.py"
    })
    
    # Should still detect the missing timeout
    assert any("requests call missing a timeout" in w for w in warnings)

def test_advanced_obfuscation_variable_aliasing():
    parser = LanguageParser()
    # Aliasing risky functions
    code = """
    import os
    h = os.system
    h("rm -rf /")
    """
    warnings = parser.parse_coding_standards({
        "name": "nuke", 
        "code_snippet": code,
        "signature": "def nuke()",
        "file": "danger.py"
    })
    
    # Current regex-based parser might FAIL this one!
    assert any("Security critical" in w for w in warnings)

def test_hallucination_robustness_junk_binary():
    parser = LanguageParser()
    # Binary junk that might contain substrings that look like risky keywords
    code = """
    def safe_op():
        junk = b"\\x00\\x01eval\\x02\\x03"
        # This is not a call to eval
        return True
    """
    warnings = parser.parse_coding_standards({
        "name": "safe_op", 
        "code_snippet": code,
        "signature": "def safe_op()",
        "file": "safe.py"
    })
    
    # Should NOT detect security critical risk
    assert not any("Security critical" in w for w in warnings)
