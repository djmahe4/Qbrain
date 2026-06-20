# quant-blm Core Intelligence Documentation

This document describes the core intelligence modules implemented in Phase 2 of the **Quantum Brain** (`quant-blm`).

The indexer wraps shell calls to the `codebase-memory-mcp` CLI tool. It handles running tools on the knowledge graph using standard JSON payloads.

- **Class**: `Indexer`
- **Responsibilities**:
  - Encapsulating raw CLI subprocess executions.
  - **Security**: Validates binary names against an allowlist (`codebase-memory-mcp`, `cbm-cli`, `qbrain-helper`) to prevent unauthorized command execution.
  - Parsing execution outputs from tools: `index_repository`, `detect_changes`, and `query_graph`.
  - Providing custom Cypher query execution helper.


## 2. Docstring & Genome Parser (`brain/docstring_parser.py`)

Retrieves functions and builds the "Docstring Genome".

- **Class**: `DocstringParser`
- **Responsibilities**:
  - Running Cypher queries to select all functions in the codebase.
  - Building the "Docstring Genome" (concatenated `name(signature) - docstring`) to feed to the embedder.

## 3. LRU Semantic Tracker (`brain/lru_tracker.py`)

Caches code symbol embeddings, tracks cache evictions, and calculates semantic drift over time.

- **Class**: `LRUSemanticCache`
- **Responsibilities**:
  - Storing embeddings in an `OrderedDict` with a maximum size parameter.
  - Tracking evicted keys to identify stale/dead code references.
  - Measuring semantic drift via distance formula.

## 4. Multi-Language Docstring Parser (`brain/language_parser.py`)

A modular parser system that extracts structured parameter, return type, and business rule genome elements from language-specific comment formats.

- **Architecture**: The `LanguageParser` delegates to language-specific modules in `brain/parsers/`.
- **Supported Languages**:
  - **Python** (`python.py`): Parses Google-style `Args:` and `Returns:` blocks.
  - **JS/TS** (`javascript.py`): Extracts JSDoc `@param` and `@returns` metadata.
  - **Solidity** (`solidity.py`): Extracts NatSpec `@param`, `@return`, `@notice`, and `@dev` rules.
  - **Go** (`go.py`): Extracts multi-line `//` block comments.
  - **Rust** (`rust.py`): Extracts `# Arguments` and `# Returns` from markdown `///` blocks.
  - **C/C++** (`cpp.py`): Extracts Doxygen annotations and `@brief` tags.


## 5. Dependency Mapper (`brain/dependency_mapper.py`)

Identifies, classifies, and maps package imports, file requires, and API communication endpoints.

- **Class**: `DependencyMapper`
- **Responsibilities**:
  - Extracting dependency relationships from the indexed graph.
  - Classifying dependencies into `external` packages, `internal` file imports, and `api` endpoints.
  - Writing `DEPENDS_ON` and `CALLS_API` graph edges back to codebase-memory-mcp.

## 6. Business Logic Mapper (`brain/business_logic_mapper.py`)

Scans function docstring genomes to classify code operations into distinct business rule types.

- **Class**: `BusinessLogicMapper`
- **Responsibilities**:
  - Extracting rules and categorizing them into: `validation`, `authorization`, `computation`, `io`, or `event`.
  - Storing extracted items as `BUSINESS_RULE` nodes connected via `IMPLEMENTS` edges to their corresponding functions.

## 7. Entrypoint Finder (`brain/entrypoint_finder.py`)

Detects the main logical execution entrypoints of the codebase using configuration parser heuristics and content-based script detection.

- **Class**: `EntrypointFinder`
- **Responsibilities**:
  - Parsing configuration files including `package.json`, `Cargo.toml`, `pyproject.toml`, and YAML settings.
  - **Heuristics**: Scans non-standard files for internal entrypoint logic (e.g., `require` calls in PHP, `__main__` guards in Python, `http.createServer` in JS).
  - Falling back to scanning standard filenames (`main.cpp`, `index.ts`, `app.py`, `main.go`) deep within the directory tree.



## 8. Quantum DataFlow Engine (`brain/dataflow_engine.py`)

Analyzes code snippets to track variable lifecycles, states, and dataflow paths.

- **Class**: `DataFlowEngine`
- **Responsibilities**:
  - **Source Detection**: Identifies external input entrypoints (e.g., `$_GET`, `request.args`).
  - **Sanitization Tracking**: Recognizes security-critical sanitization functions (e.g., `htmlspecialchars`).
  - **Sink Identification**: Maps data arrival at dangerous or terminal locations (e.g., `echo`, `query`, `os.system`).
  - **Condition Sink Mapping**: Treats control-flow conditions (`if`, `while`, etc.) containing non-constant variables as contextual sinks to map decision-point dataflows.
  - **Quantum State Assignment**: Classifies variable security states into `TAINTED`, `SAFE`, or `CONSTANT` based on flow history.
  - **Path Mapping**: Builds Mermaid-compatible dataflow paths from sources to sinks.


## 9. Dynamic Taint Classifier (`brain/taint_classifier.py`)

Dynamically classifies variable taints into semantic labels like `USER_ID`, `CREDENTIAL`, `AUTH_TOKEN`, etc.

- **Class**: `TaintClassifier`
- **Responsibilities**:
  - Reading user-defined regex pattern labels from `<vault_path>/.qbrain/.qbrain-taint-labels.yaml`.
  - Integrating `GlobalRegistry` constants to identify safe values.
  - Employing name-based pattern matching (e.g. `passwd`, `token`, `role`) as fallbacks.
  - Classifying flows to construct clean, human-readable dataflow models.

## 10. Vulnerability Scanner (`brain/vuln_scanner.py`)

Runs unified security audits across codebase symbols and tracks vulnerabilities mapped to CWE designations.

- **Class**: `VulnerabilityScanner`
- **Responsibilities**:
  - **CWE-862: Missing Authorization**: Scans public APIs and entrypoints to identify missing permission/auth checks.
  - **CWE-863: Incorrect Authorization**: Cross-references identified authorization rules against the actual code snippet to detect missing verification calls.
  - **CWE-532: Sensitive Info in Logs**: Identifies exposure of sensitive credentials flowing into print/logging functions.
  - **CWE-Mapped Taint-to-Sink Dataflow**: Checks if variables marked `TAINTED` reach any of the 25+ monitored PHP/Python sink substrings, mapping them to CWEs (XSS CWE-79, SQLi CWE-89, Command Injection CWE-78, Path Traversal CWE-22, SSRF CWE-918, etc.).
  - **CWE-798: Hardcoded Credentials**: Scans code blocks for hardcoded passwords, tokens, or private keys.
  - **CWE-400: Resource Consumption**: Flags unbounded loops (`while True`) that lack clear termination criteria or missing subprocess timeouts.
  - **CWE-312: Cleartext Storage**: Warns on cleartext writes of sensitive variables to file or persistent storage systems.
  - **Parser Warning Bridge**: Translates structural warnings emitted by the `language_parser` coding standards engine into official, severity-rated CWE findings.
