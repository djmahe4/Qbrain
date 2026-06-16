import pytest
import os
import random
import numpy as np
import yaml
from unittest.mock import MagicMock
from brain.config import Config
from brain.language_parser import LanguageParser, detect_language
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.librarian import LibrarianEngine
from brain.indexer import Indexer

def test_language_parser_missing_docstrings():
    parser = LanguageParser()
    languages = ["python", "javascript", "typescript", "solidity", "rust", "go", "cpp", "generic"]

    for lang in languages:
        # Test None docstring
        record_none = {
            "name": f"test_none_{lang}",
            "file": f"src/test.{lang}",
            "docstring": None,
            "signature": "void run()",
            "language": lang
        }
        genome_none = parser.parse(record_none)
        assert genome_none["name"] == f"test_none_{lang}"
        assert genome_none["docstring"] == ""
        assert genome_none["params"] == []
        assert genome_none["returns"] == {"type": "", "description": ""}
        assert genome_none["business_rules"] == []

        # Test empty docstring
        record_empty = {
            "name": f"test_empty_{lang}",
            "file": f"src/test.{lang}",
            "docstring": "   ",
            "signature": "void run()",
            "language": lang
        }
        genome_empty = parser.parse(record_empty)
        assert genome_empty["name"] == f"test_empty_{lang}"
        assert genome_empty["params"] == []
        assert genome_empty["returns"] == {"type": "", "description": ""}

def test_language_parser_malformed_comments():
    parser = LanguageParser()
    
    # Malformed JSDoc
    record_js = {
        "name": "jsFunc",
        "file": "src/test.js",
        "docstring": "/** @param invalid type format } foo @returns {incomplete */",
        "language": "javascript"
    }
    genome_js = parser.parse(record_js)
    assert len(genome_js["params"]) >= 0  # Should parse gracefully or return empty, no exception
    assert isinstance(genome_js["returns"], dict)

    # Malformed Python docstring (no structure, empty parameters header)
    record_py = {
        "name": "pyFunc",
        "file": "src/test.py",
        "docstring": "Parameters:\n-----------\nInvalid indented line\nReturns:\n-------",
        "language": "python"
    }
    genome_py = parser.parse(record_py)
    assert isinstance(genome_py["params"], list)
    assert "type" in genome_py["returns"]
    assert "description" in genome_py["returns"]

    # Malformed Doxygen
    record_cpp = {
        "name": "cppFunc",
        "file": "src/test.cpp",
        "docstring": "/// @param [in,out] @returns",
        "language": "cpp"
    }
    genome_cpp = parser.parse(record_cpp)
    assert isinstance(genome_cpp["params"], list)
    assert isinstance(genome_cpp["returns"], dict)

def test_stress_quantum_scorer_performance_bh():
    config = Config()
    scorer = QuantumScorer(config, MagicMock())
    
    # Generate 600 nodes (threshold for Barnes-Hut is > 500)
    nodes = []
    dim = 384  # typical embed size
    for i in range(600):
        emb = np.random.rand(dim)
        emb /= np.linalg.norm(emb)
        node = FunctionNode(
            name=f"func_{i}",
            embedding=emb,
            complexity=random.uniform(1.0, 10.0),
            side_effects=random.uniform(0.0, 1.0),
            is_exported=random.choice([True, False])
        )
        nodes.append(node)

    # Run physical simulation using Barnes-Hut quadtree
    scorer.run_simulation(nodes, iterations=5)
    
    # Check that scores were generated successfully
    for n in nodes:
        assert 0.0 <= n.business_score <= 1.0
        assert n.quantum_state in ("core-logic", "utility", "standard-module", "system-hub")

def test_stress_quantum_scorer_dense_positions():
    config = Config()
    scorer = QuantumScorer(config, MagicMock())
    
    # Create nodes with identical semantic embeddings (semantic_distance = 0) and overlapping starting positions
    emb = np.ones(128)
    emb /= np.linalg.norm(emb)
    
    nodes = [
        FunctionNode("fn1", emb.copy()),
        FunctionNode("fn2", emb.copy()),
        FunctionNode("fn3", emb.copy())
    ]
    
    # Force initial positions to be exactly identical
    for fn in nodes:
        fn.position = [0.1, 0.1]
        
    # Run simulation: should nudging solve coordinate overlaps without throwing division by zero?
    scorer.run_simulation(nodes, iterations=10)
    
    for fn in nodes:
        assert not np.isnan(fn.position[0])
        assert not np.isnan(fn.position[1])

def test_stress_librarian_lock_concurrency(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))

    # Lock acquisition
    with engine.lock():
        # A second attempt to lock from same engine instance/thread is blocked
        with pytest.raises(RuntimeError):
            with engine.lock():
                pass

def test_stress_config_merging_complex(tmp_path):
    # Setup custom override .qbrain-rules.yaml with deeply nested configs
    rules_data = {
        "history": {
            "keep_threshold": 42,
            "weights": {
                "security_change": 99,
                "behavior_change": 88
            },
            "ignore": ["*.ts", "build/"]
        }
    }
    rules_file = tmp_path / ".qbrain-rules.yaml"
    rules_file.write_text(yaml.dump(rules_data))

    config = Config()
    config.data["repo_path"] = str(tmp_path)
    config._load_rules_config()

    # Core parameters should be merged
    assert config.data["rules"]["history"]["keep_threshold"] == 42
    assert config.data["rules"]["history"]["weights"]["security_change"] == 99
    assert config.data["rules"]["history"]["weights"]["behavior_change"] == 88
    # Glob ignores overridden
    assert "*.ts" in config.data["rules"]["history"]["ignore"]
    # Fallback weights preserved
    assert config.data["rules"]["history"]["weights"]["symbol_change"] == 3

def test_language_parser_coding_standards_checks():
    parser = LanguageParser()
    
    # Test bad function naming (not verb-noun, too short/vague)
    record_bad_name = {
        "name": "data",
        "file": "src/process.py",
        "docstring": "docs",
        "signature": "def data()",
        "code_snippet": "def data():\n    pass"
    }
    res = parser.parse_coding_standards(record_bad_name)
    assert any("verb-noun pattern" in w.lower() for w in res)

    # Test function too long (> 50 lines)
    code_long = "def long_func():\n" + "\n".join([f"    x = {i}" for i in range(60)])
    record_long = {
        "name": "processData",
        "file": "src/process.py",
        "docstring": "docs",
        "signature": "def processData()",
        "code_snippet": code_long
    }
    res_long = parser.parse_coding_standards(record_long)
    assert any("too long" in w.lower() for w in res_long)

    # Test nesting check
    code_nested = "def nested_func():\n    if a:\n        if b:\n            if c:\n                if d:\n                    pass"
    record_nested = {
        "name": "processData",
        "file": "src/process.py",
        "docstring": "docs",
        "signature": "def processData()",
        "code_snippet": code_nested
    }
    res_nested = parser.parse_coding_standards(record_nested)
    assert any("deep nesting" in w.lower() for w in res_nested)


def test_language_parser_expanded_coding_standards():
    parser = LanguageParser()

    # 1. Short/vague variable name
    res1 = parser.parse_coding_standards({
        "name": "calculateSum",
        "code_snippet": "def calculateSum():\n    q = 'query'\n    return q"
    })
    assert any("short/vague variable name" in w.lower() for w in res1)

    # 2. Immutability violations
    res2 = parser.parse_coding_standards({
        "name": "updateList",
        "code_snippet": "function updateList(arr) {\n    arr.push(4);\n    return arr;\n}"
    })
    assert any("immutability violation" in w.lower() for w in res2)

    # 3. Missing try/catch on I/O
    res3 = parser.parse_coding_standards({
        "name": "fetchData",
        "code_snippet": "function fetchData() {\n    let response = fetch('url');\n    return response;\n}"
    })
    assert any("missing try/catch" in w.lower() for w in res3)

    # 4. Magic numbers check
    res4 = parser.parse_coding_standards({
        "name": "calculateArea",
        "code_snippet": "def calculateArea(r):\n    return 3.14159 * r * r"
    })
    assert any("magic number" in w.lower() for w in res4)

    # 5. Boolean parameter flags
    res5 = parser.parse_coding_standards({
        "name": "setupUser",
        "signature": "setupUser(is_active: bool)",
        "code_snippet": "def setupUser(is_active: bool):\n    pass"
    })
    assert any("boolean parameter flag" in w.lower() for w in res5)

    # 6. Ternary hell check
    res6 = parser.parse_coding_standards({
        "name": "getRating",
        "code_snippet": "const getRating = (score) => score > 90 ? 'A' : score > 80 ? 'B' : 'C';"
    })
    assert any("ternary hell" in w.lower() for w in res6)

    # 7. Stating the obvious comment check
    res7 = parser.parse_coding_standards({
        "name": "incrementCounter",
        "code_snippet": "def incrementCounter():\n    # increment x by 1\n    x += 1"
    })
    assert any("stating the obvious" in w.lower() for w in res7)

    # 8. Sequential awaits check
    res8 = parser.parse_coding_standards({
        "name": "loadDashboard",
        "code_snippet": "async function loadDashboard() {\n    const user = await fetchUser();\n    const posts = await fetchPosts();\n}"
    })
    assert any("sequential awaits" in w.lower() for w in res8)


def test_language_parser_architectural_and_performance_checks():
    parser = LanguageParser()

    # 1. Parameter count smell (5+ params in signature)
    res_param_smell = parser.parse_coding_standards({
        "name": "processData",
        "signature": "def processData(a, b, c, d, e)",
        "code_snippet": "def processData(a, b, c, d, e):\n    pass"
    })
    assert any("parameter count" in w.lower() for w in res_param_smell)

    # 2. File naming conventions: components/
    res_component_bad = parser.parse_coding_standards({
        "name": "myComponent",
        "file": "src/components/button.tsx",
        "code_snippet": "export default function button() {}"
    })
    assert any("components/" in w.lower() and "pascalcase" in w.lower() for w in res_component_bad)

    res_component_good = parser.parse_coding_standards({
        "name": "MyComponent",
        "file": "src/components/Button.tsx",
        "code_snippet": "export default function Button() {}"
    })
    assert not any("components/" in w.lower() for w in res_component_good)

    # 3. File naming conventions: hooks/
    res_hook_bad = parser.parse_coding_standards({
        "name": "useAuth",
        "file": "src/hooks/use_auth.ts",
        "code_snippet": "export function use_auth() {}"
    })
    assert any("hooks/" in w.lower() and "camelcase" in w.lower() for w in res_hook_bad)

    res_hook_good = parser.parse_coding_standards({
        "name": "useAuth",
        "file": "src/hooks/useAuth.ts",
        "code_snippet": "export function useAuth() {}"
    })
    assert not any("hooks/" in w.lower() for w in res_hook_good)

    # 4. API endpoint verb names
    res_api_bad = parser.parse_coding_standards({
        "name": "getUsers",
        "file": "src/api/get_users.ts",
        "code_snippet": "export function getUsers() {}"
    })
    assert any("api endpoint" in w.lower() and "verb" in w.lower() for w in res_api_bad)

    res_api_good = parser.parse_coding_standards({
        "name": "users",
        "file": "src/api/users.ts",
        "code_snippet": "export function users() {}"
    })
    assert not any("api endpoint" in w.lower() for w in res_api_good)

    # 5. SQL SELECT * performance check
    res_sql_bad = parser.parse_coding_standards({
        "name": "queryUsers",
        "code_snippet": "const sql = 'SELECT * FROM users';\ndb.query(sql);"
    })
    assert any("select *" in w.lower() for w in res_sql_bad)

    # 6. Input validation schema check
    res_validation_bad = parser.parse_coding_standards({
        "name": "handleRequest",
        "signature": "handleRequest(req, res)",
        "code_snippet": "function handleRequest(req, res) {\n    const data = req.body;\n}"
    })
    assert any("input validation" in w.lower() or "request/req" in w.lower() for w in res_validation_bad)

    res_validation_good = parser.parse_coding_standards({
        "name": "handleRequest",
        "signature": "handleRequest(req, res)",
        "code_snippet": "function handleRequest(req, res) {\n    const data = schema.validate(req.body);\n}"
    })
    assert not any("input validation" in w.lower() or "request/req" in w.lower() for w in res_validation_good)


def test_language_parser_language_and_api_conventions():
    parser = LanguageParser()

    # 1. Type safety check
    res_any1 = parser.parse_coding_standards({
        "name": "processData",
        "code_snippet": "const data: any = {};"
    })
    assert any("type safety" in w.lower() or "any" in w.lower() for w in res_any1)

    res_any2 = parser.parse_coding_standards({
        "name": "processData",
        "code_snippet": "const data = rawData as any;"
    })
    assert any("type safety" in w.lower() or "any" in w.lower() for w in res_any2)

    # 2. React state updates
    res_react_bad = parser.parse_coding_standards({
        "name": "MyComponent",
        "code_snippet": "setCount(count + 1);"
    })
    assert any("react state" in w.lower() or "functional update" in w.lower() for w in res_react_bad)

    res_react_good = parser.parse_coding_standards({
        "name": "MyComponent",
        "code_snippet": "setCount(prev => prev + 1);"
    })
    assert not any("react state" in w.lower() or "functional update" in w.lower() for w in res_react_good)

    # 3. Empty catch blocks
    res_catch_bad1 = parser.parse_coding_standards({
        "name": "runJob",
        "code_snippet": "try {\n  doSomething();\n} catch (e) {}"
    })
    assert any("empty catch" in w.lower() or "silent failure" in w.lower() for w in res_catch_bad1)

    res_catch_bad2 = parser.parse_coding_standards({
        "name": "runJob",
        "code_snippet": "try {\n  doSomething();\n} catch (e) {\n  // empty\n}"
    })
    assert any("empty catch" in w.lower() or "silent failure" in w.lower() for w in res_catch_bad2)

    res_catch_good = parser.parse_coding_standards({
        "name": "runJob",
        "code_snippet": "try {\n  doSomething();\n} catch (e) {\n  console.error(e);\n}"
    })
    assert not any("empty catch" in w.lower() or "silent failure" in w.lower() for w in res_catch_good)

    # 4. API response format check
    # Check under api/ path with HTTP verb method
    res_api_bad1 = parser.parse_coding_standards({
        "name": "getUsers",
        "file": "src/api/users.ts",
        "code_snippet": "res.json({ users: [] });"
    })
    assert any("success" in w.lower() and "response" in w.lower() for w in res_api_bad1)

    # Check under api/ path with endpoint file
    res_api_bad2 = parser.parse_coding_standards({
        "name": "handler",
        "file": "src/api/endpoint.ts",
        "code_snippet": "return { status: 200, body: JSON.stringify({ data: 123 }) };"
    })
    assert any("success" in w.lower() and "response" in w.lower() for w in res_api_bad2)

    # Good API response
    res_api_good = parser.parse_coding_standards({
        "name": "getUsers",
        "file": "src/api/users.ts",
        "code_snippet": "res.json({ success: true, users: [] });"
    })
    assert not any("success" in w.lower() and "response" in w.lower() for w in res_api_good)





