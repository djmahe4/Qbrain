import os
import json
import pytest
from unittest.mock import MagicMock, patch
from brain.config import Config
from brain.indexer import Indexer
from brain.commands import library
from brain.librarian import LibrarianEngine

def test_sync_library_file_size_and_loc_resolution(mocker, tmp_path):
    repo_path = os.path.join(tmp_path, "repo")
    vault_path = os.path.join(tmp_path, "vault")
    os.makedirs(repo_path)
    os.makedirs(vault_path)

    # Create dummy files in the repo
    src_dir = os.path.join(repo_path, "src")
    os.makedirs(src_dir)
    
    # 1. Normal relative file (src/myfile.py)
    rel_file = os.path.join(src_dir, "myfile.py")
    with open(rel_file, "w") as f:
        f.write("def foo():\n    pass\n")

    # Setup Config
    config_file = os.path.join(repo_path, ".quantum-brain.json")
    config_data = {"repo_path": repo_path, "vault_path": vault_path}
    with open(config_file, "w") as f:
        json.dump(config_data, f)

    mocker.patch("brain.indexer.Indexer._get_project_name", return_value="test-project")
    config = Config(config_file)
    indexer = Indexer(config)

    # Mock indexer responses
    mock_funcs = [
        {
            "name": "foo",
            "file": "src/myfile.py", # relative path
            "signature": "def foo()",
            "docstring": "",
            "language": "python"
        },
        {
            "name": "bar",
            "file": os.path.join(repo_path, "src/myfile.py"), # absolute path
            "signature": "def bar()",
            "docstring": "",
            "language": "python"
        },
        {
            "name": "baz",
            "file": "myfile.py", # Needs fallback to basename match src/myfile.py
            "signature": "def baz()",
            "docstring": "",
            "language": "python"
        }
    ]

    mocker.patch.object(Indexer, "query_graph", return_value=mock_funcs)
    mocker.patch("brain.docstring_parser.DocstringParser.get_functions_with_docstrings", return_value=mock_funcs)
    mocker.patch.object(Indexer, "get_code_snippet", return_value={"code": "def foo(): pass"})

    # Spy/Mock LibrarianEngine.export_file
    exported_files = []
    def mock_export_file(file_data):
        exported_files.append(file_data)
        
    mocker.patch.object(LibrarianEngine, "export_file", side_effect=mock_export_file)
    
    from rich.console import Console
    library.sync_library(config, indexer, Console())

    # We expect 3 file entries (or merged if they map to the same file key, wait, 
    # the key is f_path, so "src/myfile.py", absolute path, and "myfile.py" would be distinct keys in files_map)
    # Let's verify all of them successfully found the file size (> 0) and lines of code (2 lines)
    print("\n--- EXPORTED FILES ---")
    for ef in exported_files:
        print(ef)
    print("----------------------\n")
    assert len(exported_files) > 0
    for ef in exported_files:
        assert ef["lines_of_code"] == 2
        assert ef["size_bytes"] > 0


def test_sync_library_excludes_yaml_readme_and_configs(mocker, tmp_path):
    from brain.language_parser import detect_language
    # Test detect_language
    assert detect_language("config.yml") == "yaml"
    assert detect_language("config.yaml") == "yaml"
    assert detect_language("README.md") == "generic"
    assert detect_language("Cargo.toml") == "toml"
    assert detect_language("package.json") == "json"

    # Setup config
    repo_path = os.path.join(tmp_path, "repo")
    vault_path = os.path.join(tmp_path, "vault")
    os.makedirs(repo_path)
    os.makedirs(vault_path)

    config_file = os.path.join(repo_path, ".quantum-brain.json")
    with open(config_file, "w") as f:
        json.dump({"repo_path": repo_path, "vault_path": vault_path}, f)

    mocker.patch("brain.indexer.Indexer._get_project_name", return_value="test-project")
    config = Config(config_file)
    indexer = Indexer(config)

    # We mock query_graph to return a YAML file and README, plus a normal file.
    mock_all_symbols = [
        {"name": "config_yaml", "labels": ["Module"], "file": "config.yaml"},
        {"name": "readme_md", "labels": ["Module"], "file": "README.md"},
        {"name": "normal_py", "labels": ["Module"], "file": "main.py"}
    ]
    mocker.patch.object(Indexer, "query_graph", return_value=mock_all_symbols)
    mocker.patch("brain.docstring_parser.DocstringParser.get_functions_with_docstrings", return_value=[])

    # Let's spy on DataFlowEngine.analyze_snippet
    from brain.dataflow_engine import DataFlowEngine
    spy_analyze = mocker.spy(DataFlowEngine, "analyze_snippet")

    # Let's create dummy files in repo
    with open(os.path.join(repo_path, "config.yaml"), "w") as f:
        f.write("key: value\n")
    with open(os.path.join(repo_path, "README.md"), "w") as f:
        f.write("# README\n")
    with open(os.path.join(repo_path, "main.py"), "w") as f:
        f.write("print('hello')\n")

    # Run sync
    from rich.console import Console
    library.sync_library(config, indexer, Console())

    # Check analyze calls
    analyze_calls = spy_analyze.call_args_list
    assert len(analyze_calls) > 0
    for call in analyze_calls:
        assert call[0][1] not in ("yaml", "markdown", "toml", "json")


def test_sync_library_symbol_kind_differentiation(mocker, tmp_path):
    repo_path = os.path.join(tmp_path, "repo")
    vault_path = os.path.join(tmp_path, "vault")
    os.makedirs(repo_path)
    os.makedirs(vault_path)

    config_file = os.path.join(repo_path, ".quantum-brain.json")
    with open(config_file, "w") as f:
        json.dump({"repo_path": repo_path, "vault_path": vault_path}, f)

    mocker.patch("brain.indexer.Indexer._get_project_name", return_value="test-project")
    config = Config(config_file)
    indexer = Indexer(config)

    # Class node, Interface node, and normal Function node
    mock_funcs = [
        {
            "name": "MyClass",
            "file": "main.py",
            "signature": "class MyClass",
            "docstring": "A test class",
            "labels": ["Class", "symbol"],
            "language": "python"
        },
        {
            "name": "MyInterface",
            "file": "main.py",
            "signature": "interface MyInterface",
            "docstring": "A test interface",
            "labels": ["Interface", "symbol"],
            "language": "python"
        },
        {
            "name": "my_func",
            "file": "main.py",
            "signature": "def my_func()",
            "docstring": "A test func",
            "labels": ["Function", "symbol"],
            "language": "python"
        }
    ]

    mocker.patch.object(Indexer, "query_graph", return_value=mock_funcs)
    mocker.patch("brain.docstring_parser.DocstringParser.get_functions_with_docstrings", return_value=mock_funcs)
    mocker.patch.object(Indexer, "get_code_snippet", return_value={"code": "class MyClass: pass"})

    # Ensure main.py dummy exists so size is read
    with open(os.path.join(repo_path, "main.py"), "w") as f:
        f.write("class MyClass: pass\n")

    from rich.console import Console
    library.sync_library(config, indexer, Console())

    # Verify file created in vault under files/
    # Inspect content for detailed symbol specifications
    file_path = os.path.join(vault_path, "files", "main_py.md")

    assert os.path.exists(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "### Symbol: MyClass" in content
        assert "- **Kind:** `Class`" in content
        assert "### Symbol: MyInterface" in content
        assert "- **Kind:** `Interface`" in content



def test_potential_energy_majority_zero_check(mocker, tmp_path):
    repo_path = os.path.join(tmp_path, "repo")
    vault_path = os.path.join(tmp_path, "vault")
    os.makedirs(repo_path)
    os.makedirs(vault_path)

    config_file = os.path.join(repo_path, ".quantum-brain.json")
    with open(config_file, "w") as f:
        json.dump({"repo_path": repo_path, "vault_path": vault_path}, f)

    mocker.patch("brain.indexer.Indexer._get_project_name", return_value="test-project")
    config = Config(config_file)
    indexer = Indexer(config)

    # 10 mock functions (mostly zero PE, except one)
    mock_funcs = []
    for i in range(10):
        mock_funcs.append({
            "name": f"func_{i}",
            "file": "main.py",
            "signature": f"def func_{i}()",
            "docstring": f"Doc {i}",
            "language": "python"
        })

    mocker.patch.object(Indexer, "query_graph", side_effect=[
        # 1. cognitive properties query (cog_res)
        # Returns one non-zero PE, others zero
        [
            {"name": "func_0", "mass": 1.0, "potential_energy": 2.5, "archetype": "generic"}
        ] + [{"name": f"func_{i}", "mass": 1.0, "potential_energy": 0.0, "archetype": "generic"} for i in range(1, 10)],
        # 2. calls relationships
        [],
        # 3. all_symbols_res
        []
    ])
    mocker.patch("brain.docstring_parser.DocstringParser.get_functions_with_docstrings", return_value=mock_funcs)
    mocker.patch.object(Indexer, "get_code_snippet", return_value={"code": "pass"})

    with open(os.path.join(repo_path, "main.py"), "w") as f:
        f.write("pass\n")

    # Spy/mock QuantumScorer run_simulation to verify if PE simulation was triggered
    from brain.quantum_scorer import QuantumScorer
    spy_run_simulation = mocker.spy(QuantumScorer, "run_simulation")

    from rich.console import Console
    library.sync_library(config, indexer, Console())

    assert spy_run_simulation.call_count == 1


def test_sync_library_entrypoints_safety(mocker, tmp_path):
    repo_path = os.path.join(tmp_path, "repo")
    vault_path = os.path.join(tmp_path, "vault")
    os.makedirs(repo_path)
    os.makedirs(vault_path)

    config_file = os.path.join(repo_path, ".quantum-brain.json")
    with open(config_file, "w") as f:
        json.dump({"repo_path": repo_path, "vault_path": vault_path}, f)

    mocker.patch("brain.indexer.Indexer._get_project_name", return_value="test-project")
    config = Config(config_file)
    indexer = Indexer(config)

    # 1. Force SystemicAuditor or something in the try-block to raise exception
    # so entrypoints remains unbound in that block.
    from brain.systemic_auditor import SystemicAuditor
    mocker.patch.object(SystemicAuditor, "__init__", side_effect=ValueError("Forced audit failure"))

    mocker.patch.object(Indexer, "query_graph", return_value=[])
    mocker.patch("brain.docstring_parser.DocstringParser.get_functions_with_docstrings", return_value=[])
    # Mock BranchDiff to avoid Git-related errors during comparison
    mocker.patch("brain.branch_diff.BranchDiff.get_default_branch", return_value="main")
    mocker.patch("brain.branch_diff.BranchDiff.compare_branches", return_value={"modified_files": [], "insertions": 0, "deletions": 0})

    # library.sync_library should NOT crash and should successfully complete execution
    spy_export_branch_diff = mocker.spy(LibrarianEngine, "export_branch_diff")
    
    from rich.console import Console
    library.sync_library(config, indexer, Console())
    
    assert spy_export_branch_diff.call_count == 1




