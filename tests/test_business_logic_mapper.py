"""
TDD: RED Phase tests for brain.business_logic_mapper
Tests that the BusinessLogicMapper correctly:
- Tags functions with business rule categories
- Writes BUSINESS_RULE nodes and IMPLEMENTS edges to the MCP graph
"""
import pytest
from unittest.mock import MagicMock
from brain.business_logic_mapper import BusinessLogicMapper, BusinessRule, RULE_CATEGORIES


# ─────────────────────────── RULE_CATEGORIES constant ───────────────────────────

def test_rule_categories_exist():
    """Standard categories must be present."""
    required = {"validation", "authorization", "computation", "io", "event"}
    assert required.issubset(set(RULE_CATEGORIES))


# ─────────────────────────── BusinessRule ───────────────────────────

def test_business_rule_construction():
    rule = BusinessRule(
        category="authorization",
        description="Only owner can call this function.",
        source_function="transferOwnership",
        confidence=0.92
    )
    assert rule.category == "authorization"
    assert rule.confidence == pytest.approx(0.92)

def test_business_rule_invalid_category():
    with pytest.raises(ValueError):
        BusinessRule("unknown_cat", "desc", "func", 0.5)

def test_business_rule_confidence_bounds():
    with pytest.raises(ValueError):
        BusinessRule("validation", "desc", "func", confidence=1.5)
    with pytest.raises(ValueError):
        BusinessRule("validation", "desc", "func", confidence=-0.1)


# ─────────────────────────── extract_rules_from_genome ───────────────────────────

SOLIDITY_GENOME = {
    "name": "transferOwnership",
    "language": "solidity",
    "docstring": "Transfers ownership. Only current owner may call.",
    "business_rules": ["Only owner can call", "Validates new owner is not zero address"],
    "params": [{"name": "newOwner", "type": "address", "description": "New owner address"}],
    "returns": {"type": "bool", "description": "True if successful"},
}

VALIDATION_GENOME = {
    "name": "validateInput",
    "language": "python",
    "docstring": "Validates user input against schema requirements.",
    "business_rules": ["Checks field length", "Ensures email format is valid"],
    "params": [{"name": "data", "type": "dict", "description": "Input data"}],
    "returns": {"type": "bool", "description": "True if valid"},
}

IO_GENOME = {
    "name": "fetchUserData",
    "language": "typescript",
    "docstring": "Fetches user data from the database and external API.",
    "business_rules": [],
    "params": [],
    "returns": {"type": "object", "description": "User record"},
}

def _make_mapper():
    indexer = MagicMock()
    indexer.query_graph.return_value = []
    return BusinessLogicMapper(indexer)

def test_extract_rules_authorization_category():
    mapper = _make_mapper()
    rules = mapper.extract_rules(SOLIDITY_GENOME)
    categories = [r.category for r in rules]
    assert "authorization" in categories

def test_extract_rules_validation_category():
    mapper = _make_mapper()
    rules = mapper.extract_rules(VALIDATION_GENOME)
    categories = [r.category for r in rules]
    assert "validation" in categories

def test_extract_rules_io_from_docstring():
    mapper = _make_mapper()
    rules = mapper.extract_rules(IO_GENOME)
    categories = [r.category for r in rules]
    assert "io" in categories

def test_extract_rules_returns_business_rule_objects():
    mapper = _make_mapper()
    rules = mapper.extract_rules(SOLIDITY_GENOME)
    assert all(isinstance(r, BusinessRule) for r in rules)

def test_extract_rules_confidence_within_bounds():
    mapper = _make_mapper()
    rules = mapper.extract_rules(VALIDATION_GENOME)
    for r in rules:
        assert 0.0 <= r.confidence <= 1.0

def test_extract_rules_empty_genome():
    mapper = _make_mapper()
    empty = {"name": "noOp", "language": "python", "docstring": "", "business_rules": [], "params": [], "returns": {}}
    rules = mapper.extract_rules(empty)
    # May return empty or only low-confidence rules — should not crash
    assert isinstance(rules, list)


# ─────────────────────────── write_rules_to_graph ───────────────────────────

def test_write_rules_creates_business_rule_nodes():
    indexer = MagicMock()
    indexer.query_graph.return_value = []
    mapper = BusinessLogicMapper(indexer)

    rules = [
        BusinessRule("authorization", "Only owner can call.", "transferOwnership", 0.9),
        BusinessRule("validation", "Validates new owner is not zero.", "transferOwnership", 0.85),
    ]
    mapper.write_rules_to_graph(rules)

    assert indexer.query_graph.call_count >= 1
    cypher_calls = [c[0][0] for c in indexer.query_graph.call_args_list]
    combined = " ".join(cypher_calls)
    assert "BUSINESS_RULE" in combined or "BusinessRule" in combined

def test_write_rules_creates_implements_edges():
    indexer = MagicMock()
    indexer.query_graph.return_value = []
    mapper = BusinessLogicMapper(indexer)

    rules = [BusinessRule("authorization", "Only owner.", "myFunc", 0.9)]
    mapper.write_rules_to_graph(rules)

    cypher_calls = [c[0][0] for c in indexer.query_graph.call_args_list]
    combined = " ".join(cypher_calls)
    assert "IMPLEMENTS" in combined

def test_write_rules_no_op_on_empty():
    indexer = MagicMock()
    mapper = BusinessLogicMapper(indexer)
    mapper.write_rules_to_graph([])
    indexer.query_graph.assert_not_called()


# ─────────────────────────── map_all (integration-style) ───────────────────────────

def test_map_all_processes_multiple_genomes():
    indexer = MagicMock()
    indexer.query_graph.return_value = []
    mapper = BusinessLogicMapper(indexer)

    genomes = [SOLIDITY_GENOME, VALIDATION_GENOME, IO_GENOME]
    all_rules = mapper.map_all(genomes)

    assert isinstance(all_rules, list)
    # At least some rules should be extracted across 3 genomes
    assert len(all_rules) >= 2

def test_map_all_writes_to_graph():
    indexer = MagicMock()
    indexer.query_graph.return_value = []
    mapper = BusinessLogicMapper(indexer)

    mapper.map_all([SOLIDITY_GENOME])
    # map_all should also write to graph
    assert indexer.query_graph.call_count >= 1

def test_map_all_returns_rules_for_empty_list():
    indexer = MagicMock()
    mapper = BusinessLogicMapper(indexer)
    result = mapper.map_all([])
    assert result == []
