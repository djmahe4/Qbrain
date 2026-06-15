"""
TDD: RED Phase tests for brain.dependency_mapper
Tests that the DependencyMapper correctly queries MCP graph for imports/requires/calls,
constructs DependencyNode objects, and writes edges back to the graph.
"""
import pytest
from unittest.mock import MagicMock, call, patch
from brain.dependency_mapper import DependencyMapper, DependencyNode


# ─────────────────────────── DependencyNode ───────────────────────────

def test_dependency_node_construction():
    node = DependencyNode(
        name="axios",
        dep_type="external",
        source_file="src/api.ts",
        target="axios"
    )
    assert node.name == "axios"
    assert node.dep_type == "external"
    assert node.source_file == "src/api.ts"
    assert node.target == "axios"

def test_dependency_node_types():
    """dep_type must be one of: external, internal, api"""
    with pytest.raises(ValueError):
        DependencyNode("bad", dep_type="unknown_type", source_file="x.py", target="y")


# ─────────────────────────── MCP Graph Query ───────────────────────────

MOCK_IMPORT_RESULTS = [
    {"name": "axios", "types": ["ExternalImport"], "file": "src/api.ts", "target": "axios"},
    {"name": "os", "types": ["StdlibImport"], "file": "brain/config.py", "target": "os"},
    {"name": "./utils", "types": ["RelativeImport"], "file": "src/main.ts", "target": "./utils"},
    {"name": "IERC20", "types": ["SolidityImport"], "file": "contracts/Vault.sol", "target": "@openzeppelin/contracts/token/ERC20/IERC20.sol"},
]

def _make_indexer(results):
    indexer = MagicMock()
    indexer.persistence = MagicMock()
    indexer.query_graph.return_value = results
    return indexer

def test_get_dependencies_calls_mcp():
    """DependencyMapper queries the MCP graph using a broad query."""
    indexer = _make_indexer(MOCK_IMPORT_RESULTS)
    mapper = DependencyMapper(indexer)
    mapper.get_dependencies()

    # Must have called query_graph
    indexer.query_graph.assert_called_once()
    # Query should use the broad MATCH (d) syntax
    query_arg = indexer.query_graph.call_args[0][0]
    assert "MATCH (d)" in query_arg
    assert "labels(d)" in query_arg

def test_get_dependencies_returns_dependency_nodes():
    indexer = _make_indexer(MOCK_IMPORT_RESULTS)
    mapper = DependencyMapper(indexer)
    deps = mapper.get_dependencies()

    assert len(deps) == 4
    assert all(isinstance(d, DependencyNode) for d in deps)

def test_get_dependencies_classifies_external():
    indexer = _make_indexer(MOCK_IMPORT_RESULTS)
    mapper = DependencyMapper(indexer)
    deps = mapper.get_dependencies()

    axios_dep = next((d for d in deps if d.name == "axios"), None)
    assert axios_dep is not None
    assert axios_dep.dep_type == "external"

def test_get_dependencies_classifies_internal():
    indexer = _make_indexer(MOCK_IMPORT_RESULTS)
    mapper = DependencyMapper(indexer)
    deps = mapper.get_dependencies()

    utils_dep = next((d for d in deps if "./utils" in d.name or "utils" in d.target), None)
    assert utils_dep is not None
    assert utils_dep.dep_type == "internal"

def test_get_dependencies_handles_empty_graph():
    indexer = _make_indexer([])
    mapper = DependencyMapper(indexer)
    deps = mapper.get_dependencies()
    assert deps == []

def test_get_dependencies_handles_dict_response():
    """Indexer may return {results: [...]} dict format."""
    indexer = _make_indexer({"results": MOCK_IMPORT_RESULTS})
    mapper = DependencyMapper(indexer)
    deps = mapper.get_dependencies()
    assert len(deps) == 4


# ─────────────────────────── API call mapping ───────────────────────────

MOCK_API_CALLS = [
    {"name": "fetchUser", "types": ["APICall"], "file": "src/user.ts", "target": "https://api.example.com/users"},
    {"name": "sendRequest", "types": ["HTTPCall"], "file": "brain/indexer.py", "target": "http://localhost:3000"},
]

def test_get_api_calls_classified_as_api():
    indexer = _make_indexer(MOCK_API_CALLS)
    mapper = DependencyMapper(indexer)
    deps = mapper.get_dependencies()
    api_deps = [d for d in deps if d.dep_type == "api"]
    assert len(api_deps) == 2


# ─────────────────────────── write_to_graph ───────────────────────────

def test_write_to_graph_persists_locally():
    """write_to_graph should call indexer.persistence.persist_entanglement."""
    indexer = _make_indexer([])
    mapper = DependencyMapper(indexer)

    deps = [
        DependencyNode("axios", "external", "src/api.ts", "axios"),
        DependencyNode("./utils", "internal", "src/main.ts", "./utils"),
    ]
    mapper.write_to_graph(deps)

    # Verify call to persistence manager
    assert indexer.persistence.persist_entanglement.call_count == 2
    calls = indexer.persistence.persist_entanglement.call_args_list
    assert calls[0][0][0] == "axios"
    assert calls[1][0][0] == "./utils"

def test_write_to_graph_no_ops_on_empty():
    indexer = _make_indexer([])
    mapper = DependencyMapper(indexer)
    mapper.write_to_graph([])
    # Should not write anything if no deps
    assert not indexer.persistence.persist_entanglement.called

def test_write_to_graph_api_edges():
    indexer = _make_indexer([])
    mapper = DependencyMapper(indexer)
    deps = [DependencyNode("fetchUser", "api", "src/user.ts", "https://api.example.com/users")]
    mapper.write_to_graph(deps)

    # Check if persistence was called with 'api' type
    assert indexer.persistence.persist_entanglement.called
    assert indexer.persistence.persist_entanglement.call_args[0][2] == "api"


# ─────────────────────────── build_dependency_summary ───────────────────────────

def test_build_summary_groups_by_file():
    indexer = _make_indexer([])
    mapper = DependencyMapper(indexer)
    deps = [
        DependencyNode("axios", "external", "src/api.ts", "axios"),
        DependencyNode("lodash", "external", "src/api.ts", "lodash"),
        DependencyNode("./db", "internal", "src/users.ts", "./db"),
    ]
    summary = mapper.build_dependency_summary(deps)

    assert "src/api.ts" in summary
    assert "src/users.ts" in summary
    assert len(summary["src/api.ts"]) == 2

def test_build_summary_empty():
    indexer = _make_indexer([])
    mapper = DependencyMapper(indexer)
    summary = mapper.build_dependency_summary([])
    assert summary == {}
