"""
TDD: RED Phase tests for brain.language_parser
Tests multi-language docstring extraction: Python, JS/TS (JSDoc), Solidity (NatSpec), Go, Rust.
"""
import pytest
from brain.language_parser import (
    LanguageParser,
    extract_business_rules,
    extract_params,
    extract_returns,
    detect_language,
    build_genome,
)


# ─────────────────────────── detect_language ───────────────────────────

def test_detect_language_from_extension_python():
    assert detect_language("contracts/vault.py") == "python"

def test_detect_language_from_extension_js():
    assert detect_language("src/utils.js") == "javascript"

def test_detect_language_from_extension_ts():
    assert detect_language("src/api.ts") == "typescript"

def test_detect_language_from_extension_tsx():
    assert detect_language("components/App.tsx") == "typescript"

def test_detect_language_from_extension_solidity():
    assert detect_language("contracts/Token.sol") == "solidity"

def test_detect_language_from_extension_go():
    assert detect_language("pkg/handler.go") == "go"

def test_detect_language_from_extension_rust():
    assert detect_language("src/main.rs") == "rust"

def test_detect_language_unknown_falls_back_to_generic():
    assert detect_language("README.md") == "generic"

def test_detect_language_explicit_override():
    """Language field in MCP graph always wins over file extension."""
    parser = LanguageParser()
    result = parser.parse(
        {"name": "myFunc", "language": "solidity", "file": "src/foo.py", "docstring": ""}
    )
    assert result["language"] == "solidity"


# ─────────────────────────── Python docstrings ───────────────────────────

PYTHON_DOCSTRING = """
Calculate the compound interest.

Args:
    principal (float): The principal amount.
    rate (float): Annual interest rate.
    periods (int): Number of compounding periods.

Returns:
    float: The total amount after interest.
"""

def test_python_extract_params():
    params = extract_params(PYTHON_DOCSTRING, "python")
    assert len(params) == 3
    names = [p["name"] for p in params]
    assert "principal" in names
    assert "rate" in names
    assert "periods" in names

def test_python_extract_returns():
    ret = extract_returns(PYTHON_DOCSTRING, "python")
    assert ret["type"] == "float"
    assert "total amount" in ret["description"].lower()


# ─────────────────────────── JSDoc (JS / TS) ───────────────────────────

JSDOC = """
/**
 * @description Transfers tokens between wallets.
 * @param {string} from - Sender address.
 * @param {string} to - Recipient address.
 * @param {number} amount - Amount to transfer.
 * @returns {boolean} True if transfer succeeded.
 */
"""

def test_jsdoc_extract_params():
    params = extract_params(JSDOC, "javascript")
    assert len(params) == 3
    names = [p["name"] for p in params]
    assert "from" in names
    assert "to" in names
    assert "amount" in names

def test_jsdoc_extract_returns():
    ret = extract_returns(JSDOC, "javascript")
    assert ret["type"] == "boolean"
    assert "transfer" in ret["description"].lower()

def test_jsdoc_extract_params_typescript():
    """TS uses same JSDoc format."""
    params = extract_params(JSDOC, "typescript")
    assert len(params) == 3

def test_jsdoc_no_params_returns_empty():
    doc = "/** Simple getter. */"
    params = extract_params(doc, "javascript")
    assert params == []


# ─────────────────────────── Solidity NatSpec ───────────────────────────

NATSPEC = """
/**
 * @notice Transfers ownership of the contract.
 * @dev Only the current owner can call this function.
 * @param newOwner The address of the new owner.
 * @return success True if the transfer was successful.
 */
"""

def test_natspec_extract_params():
    params = extract_params(NATSPEC, "solidity")
    assert len(params) == 1
    assert params[0]["name"] == "newOwner"

def test_natspec_extract_returns():
    ret = extract_returns(NATSPEC, "solidity")
    assert "success" in ret["description"].lower() or "transfer" in ret["description"].lower()

def test_natspec_extract_business_rules_notice():
    rules = extract_business_rules(NATSPEC, "solidity")
    assert any("ownership" in r.lower() for r in rules)

def test_natspec_extract_business_rules_dev():
    rules = extract_business_rules(NATSPEC, "solidity")
    assert any("owner" in r.lower() for r in rules)


# ─────────────────────────── Go docstrings ───────────────────────────

GO_COMMENT = """
// HandleTransfer processes an incoming transfer request.
// It validates the sender, checks balances, and updates the ledger.
// Returns an error if the transfer cannot be completed.
"""

def test_go_extract_business_rules():
    rules = extract_business_rules(GO_COMMENT, "go")
    # Should extract the meaningful comment lines
    assert len(rules) >= 1
    full_text = " ".join(rules).lower()
    assert "transfer" in full_text or "balance" in full_text

def test_go_no_params_from_comment():
    """Go comments don't have structured @param tags."""
    params = extract_params(GO_COMMENT, "go")
    assert params == []


# ─────────────────────────── Rust docstrings ───────────────────────────

RUST_DOC = """
/// Calculates the SHA-256 hash of the given input.
///
/// # Arguments
/// * `data` - The raw bytes to hash.
///
/// # Returns
/// A 32-byte array containing the SHA-256 digest.
"""

def test_rust_extract_params():
    params = extract_params(RUST_DOC, "rust")
    assert len(params) == 1
    assert params[0]["name"] == "data"

def test_rust_extract_returns():
    ret = extract_returns(RUST_DOC, "rust")
    assert "32-byte" in ret["description"] or "sha-256" in ret["description"].lower()


# ─────────────────────────── C/C++ docstrings ───────────────────────────

CPP_DOCSTRING = """
/**
 * @brief Performs a high-precision matrix multiplication.
 * @param matrix_a The left-hand side matrix data.
 * @param matrix_b The right-hand side matrix data.
 * \\param size The dimension of the square matrices.
 * @return The product matrix.
 */
"""

def test_cpp_extract_params():
    params = extract_params(CPP_DOCSTRING, "cpp")
    assert len(params) == 3
    names = [p["name"] for p in params]
    assert "matrix_a" in names
    assert "matrix_b" in names
    assert "size" in names

def test_cpp_extract_returns():
    ret = extract_returns(CPP_DOCSTRING, "cpp")
    assert "product matrix" in ret["description"].lower()

def test_cpp_extract_business_rules():
    rules = extract_business_rules(CPP_DOCSTRING, "cpp")
    assert any("matrix multiplication" in r.lower() for r in rules)



# ─────────────────────────── LanguageParser.parse() ───────────────────────────

def test_language_parser_parse_solidity_full():
    """End-to-end parsing of a Solidity function record from MCP graph."""
    record = {
        "name": "transferOwnership",
        "file": "contracts/Ownable.sol",
        "language": "solidity",
        "docstring": NATSPEC,
        "signature": "address newOwner",
    }
    parser = LanguageParser()
    genome = parser.parse(record)

    assert genome["name"] == "transferOwnership"
    assert genome["language"] == "solidity"
    assert len(genome["params"]) == 1
    assert genome["params"][0]["name"] == "newOwner"
    assert len(genome["business_rules"]) >= 1

def test_language_parser_parse_typescript_jsdoc():
    record = {
        "name": "transferTokens",
        "file": "src/wallet.ts",
        "docstring": JSDOC,
        "signature": "from: string, to: string, amount: number",
    }
    parser = LanguageParser()
    genome = parser.parse(record)

    assert genome["language"] == "typescript"
    assert len(genome["params"]) == 3
    assert genome["returns"]["type"] == "boolean"

def test_language_parser_parse_missing_docstring():
    """Should not crash on functions with no docstring."""
    record = {"name": "noDoc", "file": "src/helper.ts"}
    parser = LanguageParser()
    genome = parser.parse(record)
    assert genome["name"] == "noDoc"
    assert genome["params"] == []
    assert genome["business_rules"] == []


# ─────────────────────────── build_genome() ───────────────────────────

def test_build_genome_includes_business_rules():
    genome_dict = {
        "name": "mint",
        "signature": "address to, uint256 amount",
        "docstring": "Mints new tokens.",
        "language": "solidity",
        "params": [{"name": "to", "type": "address", "description": "recipient"}],
        "returns": {"type": "bool", "description": "success"},
        "business_rules": ["Only owner can call", "Validates supply cap"],
    }
    result = build_genome(genome_dict)
    # Genome string must be a non-empty semantic string
    assert "mint" in result
    assert len(result) > 10
    # Business rules should be part of the genome for embedding
    assert "owner" in result.lower() or "supply" in result.lower()
