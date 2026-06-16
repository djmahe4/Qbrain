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
 │    ├── branch_diff.md    # Branch divergence & semantic diff summaries
 │    ├── recent/           # High-relevance commits waiting for inspection
 │    └── archive/          # Archived historical changes
 ├── rules/                 # Extracted coding invariants and business policies
 └── baseline.md            # Original HEAD state baseline snapshot
```

---

## 2. Concurrency Locking (.qbrain.lock)

To prevent multiple processes from corrupting the vault, the librarian uses a robust, retry-aware locking mechanism:

1. **Acquire**: Attempts to write a `.qbrain.lock` file.
2. **Metadata Payload**: Writes JSON metadata (`pid` and `create_time`) to the lock file.
3. **Backward Compatibility**: Gracefully parses legacy raw PID integers or string values alongside the JSON format.
4. **Atomic Creation**: Uses `'x'` mode to prevent race conditions during file creation.
5. **Retry Logic**: If the lock is held, it waits and retries for up to 30 seconds before timing out.
6. **Stale Lock Cleanup**: Automatically identifies and clears stale locks if the recorded PID is no longer active on the system.
7. **Release**: Ensures the lock is removed even if the process crashes or an exception is raised.

---

## 3. Path Sanitization & Security

The Librarian implements a strict security boundary for vault exports:

- **Traversal Prevention**: Every file write is validated against the base `vault_path` using `os.path.abspath`. 
- **Blocked Writes**: Any attempt to write outside the configured vault directory (e.g., using `../../` in a symbol name) triggers a `ValueError` and halts the sync.

---

## 4. Symbol Page Enrichment

Every symbol exported to `symbols/*.md` is fully enriched with physical, semantic, and structural data:

- **YAML Frontmatter**: Includes physical metrics (`mass` representing complexity, `potential_energy` representing drift pressure) and the semantic classification (`archetype`).
- **Implementation**: Syntax-highlighted source code block of the function or class.
- **Semantic Neighbors**: Linked Wiki-links to the top 3 semantically closest symbols, evaluated using cosine similarity on high-dimensional code embeddings.
- **Entanglements**: Lists of inbound callers and outbound callees to map static dependency paths.
- **Variable States Table**: Every symbol now includes a table detailing each variable's security state (`TAINTED`, `SAFE`, `CONSTANT`).
- **Dataflow Graph**: Mermaid diagrams visualizing the path from source (e.g. `$_GET`) to sink (e.g. `echo`).

```markdown
---
type: symbol
name: calculateTrajectory
language: python
file: physics/trajectory.py
signature: def calculateTrajectory(velocity, angle)
mass: 4.5
potential_energy: 12.0
archetype: calculation-engine
---

# Symbol: calculateTrajectory

## Documentation
Calculates projectile trajectory.

...

## Variable States
| Variable | State | Current Context |
|:---|:---|:---|
| `$name` | `SAFE` | calculateTrajectory |

## Dataflow Graph
```mermaid
graph LR
  P0_SRC["$_GET"] -- "$name (SAFE)" --> P0_SINK["echo"]
```

## Semantic Neighbors
- [[simulateOrbit]] (95.0% similarity)
- [[getGravityField]] (88.0% similarity)

## Entanglements
### Inbound Callers
- [[runSimulation]]
- [[main]]

### Outbound Callees
- [[math.cos]]
- [[math.sin]]

## Implementation
```python
def calculateTrajectory(velocity, angle):
    g = 9.81
    return (velocity * math.cos(angle), velocity * math.sin(angle) - 0.5 * g)
```
```

---

## 5. Behavior Flow Dual-Representation & Sanitization

Behaviors are written to the vault using a hybrid markdown format designed for both human visualization and machine-parsing:

- **Human Visualization**: Mermaid class/state diagrams (`stateDiagram-v2`) showing states, flows, and execution path conditions.
- **State Sanitization**: Spaces, hyphens, and special characters in state names are cleaned using `_state_id` formatting, and aliased using `state "Original Name" as Safe_ID` to prevent Mermaid syntax compiler crashes.
- **Machine/LLM Representation**: Structured YAML Frontmatter metadata containing states lists, endpoints, triggers, and signatures.

---

## 6. Consolidated Central Reports

The Librarian aggregates repository metadata into dedicated index pages under `rules/` and `changes/`:

1. **Security Vulnerabilities & CWE Violations (`rules/vulnerabilities.md`)**: A consolidated table detailing detected security issues, severity levels, and links to source files/symbols.
2. **Cognitive & Complexity Hotspots (`rules/hotspots.md`)**: High mass functions (complexity hotspots) and high potential energy functions (drift/attention hotspots).
3. **Semantic Archetypes (`rules/archetypes.md`)**: Symbols grouped by their structural and behavioral roles (e.g., `data-model`, `calculation-engine`, etc.).
4. **Git Branch Diff (`changes/branch_diff.md`)**: Calculates semantic distance, churn, and relevance scores when comparing the active workspace against the base branch (e.g., `main`).

---

## 7. Greenfield Initialization Fallback

If `quant-blm` is initialized or indexed in a workspace directory where `.git` is missing:

1. It runs `git init` to set up local version control.
2. It generates a default rules configuration `.qbrain-rules.yaml` prescribing keep thresholds, weights for commits, and glob filters.
3. It initializes the baseline vault template folder structure for developers to start recording architecture decisions.
4. The brain analyzes user-provided keywords (e.g., "high-throughput payment gateway", "solidity dex", "real-time chat service") and outputs:
   - A recommended tech stack (e.g., choice of language, databases, frameworks).
   - A custom `.qbrain-rules.yaml` containing matching keywords, weights, and parsing regexes tailored to the selected languages.
   - A step-by-step implementation plan and architectural guidelines to write code that aligns with the target design.

---

## 8. Docstring & Quality Invariants Warnings

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
