# 📚 Learning Librarian & Obsidian Vault Exporter

The **Learning Librarian** (`brain/librarian.py`) acts as the knowledge synchronizer between the Neo4j-based memory representation (`codebase-memory-mcp`) and a human-readable local Obsidian vault.

---

## 1. Vault Directory Structure

When `setup_vault()` is run, the engine creates the following folder hierarchy under the configured vault path:

```text
obsidian_vault/
 ├── symbols/               # Exported symbol pages (functions, classes, variables)
 ├── files/                 # File structural maps and file-level metrics
 ├── behaviors/             # User journeys, execution flows, and state machines
 ├── changes/
 │    ├── recent/           # High-relevance commits waiting for inspection
 │    └── archive/          # Archived historical changes
 ├── rules/                 # Extracted coding invariants and business policies
 └── baseline.md            # Original HEAD state baseline snapshot
```

---

## 2. Concurrency Locking (.qbrain.lock)

To prevent multiple processes from corrupting the vault, the librarian uses a robust, retry-aware locking mechanism:

1. **Acquire**: Attempts to write a `.qbrain.lock` file containing the current PID.
2. **Atomic Creation**: Uses `'x'` mode to prevent race conditions during file creation.
3. **Retry Logic**: If the lock is held, it waits and retries for up to 30 seconds before timing out.
4. **Stale Lock Cleanup**: Automatically identifies and clears stale locks if the recorded PID is no longer active on the system.
5. **Release**: Ensures the lock is removed even if the process crashes or an exception is raised.

---

## 3. Path Sanitization & Security

The Librarian implements a strict security boundary for vault exports:

- **Traversal Prevention**: Every file write is validated against the base `vault_path` using `os.path.abspath`. 
- **Blocked Writes**: Any attempt to write outside the configured vault directory (e.g., using `../../` in a symbol name) triggers a `ValueError` and halts the sync.

---

## 4. Behavior Flow Dual-Representation

Behaviors are written to the vault using a hybrid markdown format designed for both human visualization and machine-parsing:


- **Human Visualization**: Mermaid class/state diagrams (`stateDiagram-v2`) showing states, flows, and execution path conditions.
- **Machine/LLM Representation**: Structured YAML Frontmatter metadata containing states lists, endpoints, triggers, and signatures.

````markdown
---
type: behavior
name: auth-flow
states: [REQUEST, VALIDATE, SUCCESS, FAILURE]
---

# Behavior: auth-flow

## State Machine

```mermaid
stateDiagram-v2
    REQUEST
    VALIDATE
    SUCCESS
    FAILURE
    REQUEST --> VALIDATE
    VALIDATE --> SUCCESS: valid_credentials
    VALIDATE --> FAILURE: invalid_credentials
```
````

---

## 5. Greenfield Initialization Fallback

If `quant-blm` is initialized or indexed in a workspace directory where `.git` is missing:

1. It runs `git init` to set up local version control.
2. It generates a default rules configuration `.qbrain-rules.yaml` prescribing keep thresholds, weights for commits, and glob filters.
3. It initializes the baseline vault template folder structure for developers to start recording architecture decisions.
4. The brain analyzes user-provided keywords (e.g., "high-throughput payment gateway", "solidity dex", "real-time chat service") and outputs:
   - A recommended tech stack (e.g., choice of language, databases, frameworks).
   - A custom `.qbrain-rules.yaml` containing matching keywords, weights, and parsing regexes tailored to the selected languages.
   - A step-by-step implementation plan and architectural guidelines to write code that aligns with the target design.

---

## 6. Docstring & Quality Invariants Warnings

During `qbrain library sync`, the system evaluates the structural completeness of each symbol's documentation:
- **Missing Docstrings**: Triggers a warning if a function or method has an empty or missing comment block.
- **Malformed Docstrings**: Compares signature parameters against documented `@param` parameters. For languages like Python, JS/TS, C++, Go, Rust, and Solidity, a warning is raised if parameters declared in the signature are completely undocumented.
- **Reporting**: Discovered violations are compiled and saved to `rules/warnings.md` in the Obsidian vault, using standard Markdown tables with internal linkages.

### Coding Standards & Vibe Auditing

The Librarian runs an exhaustive semantic analysis suite on function code snippets:

1. **Security (Vibe Auditor)**:
   - **Dangerous Functions**: Detects usage of `eval()`, `exec()`, `os.system()`, or `subprocess`.
   - **Credentials**: Identifies hardcoded passwords, tokens, or API keys in string literals.
   - **Deserialization**: Flags unsafe `pickle` or `yaml.load` calls without safe loaders.
   - **Path Traversal**: Warns on unvalidated string concatenation in `open()` calls.
   - **Permissions**: Detects insecure file permission settings (e.g., `chmod 777`).
   - **Obfuscation**: Identifies variable aliasing of risky functions (e.g., `h = os.system`).

2. **Robustness & Async Safety**:
   - **HTTP Timeouts**: Warns if `requests` calls are missing an explicit `timeout`.
   - **Async Performance**: Flags synchronous blocking calls (like `time.sleep` or `requests.get`) inside `async def` functions.
   - **Unbounded Loops**: Identifies `while True` blocks without clear exit conditions.
   - **Silent Failures**: Flags empty `catch` blocks or Python `except: pass` patterns.

3. **Memory & Concurrency**:
   - **Collection Growth**: Heuristically identifies collections (lists, sets) that append inside loops without size checks or clearing.
   - **Cache Hygiene**: Warns on `@lru_cache` usage without an explicit `maxsize`.
   - **Global State**: Flags usage of the `global` keyword in concurrent contexts.

4. **Frontend & API Patterns**:
   - **Naming**: Enforces `PascalCase` for React components and `useCamelCase` for hooks.
   - **React State**: Recommends functional updates (`setVal(v => v + 1)`) over direct value assignment.
   - **API Schema**: Checks for Zod/Yup/Joi validation schemas when receiving requests.
   - **JSON Format**: Ensures API responses include a mandatory `success` boolean field.

