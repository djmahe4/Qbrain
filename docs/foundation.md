# quant-blm Foundation Documentation

This document describes the foundation modules implemented in Phase 1 of the **Quantum Brain** (`quant-blm`).

The foundation relies on a central configuration module (`brain/config.py`) which reads `.quantum-brain.json` from the repository root. The project is managed using `uv` and follows PEP 621 standards.


### Default Configuration Structure

```json
{
  "repo_path": ".",
  "cbm_binary": "codebase-memory-mcp",
  "embedder_model": "all-MiniLM-L6-v2",
  "lru_maxsize": 512,
  "quantum_gravity_constant": 1.0,
  "repulsive_constant": 0.1,
  "business_collapse_threshold": 0.65,
  "cron": {
    "git_diff_check_interval_minutes": 5,
    "branch_lru_sync_interval_minutes": 15,
    "full_reindex_cron": "0 2 * * *"
  },
  "branch_diff": {
    "semantic_drift_threshold": 0.25,
    "lru_branch_pairs_maxsize": 32
  }
}
```

### Configuration Loader (`brain/config.py`)

The loader resolves the configuration file by searching current directory and its parent directories. It automatically merges user configurations with the default system properties.

- **Class**: `Config`
- **Properties**:
  - `repo_path`: Absolute path to target repository.
  - `cbm_binary`: Binary name or command prefix for `codebase-memory-mcp`.
  - `embedder_model`: Name of the sentence-transformers model.
  - `lru_maxsize`: LRU cache size limit.
  - `quantum_gravity_constant`: Gravitational constant `G`.
  - `repulsive_constant`: Repulsion constant `k_repulse`.
  - `business_collapse_threshold`: Threshold for collapsing superposition to business state.
## Dual-Persistence Intelligence Sidecar (`brain/persistence_manager.py`)

To support writable state discovery (which the primary memory graph currently restricts), the system implements a "Mind" sidecar using a project-local SQLite database.

- **Class**: `PersistenceManager`
- **Data Stores**:
  - **Internal Mind (SQLite)**: Stores writable internal beliefs, physics scores (mass, PE), security entanglements, and dataflow results. This database is named `.qbrain-mind-<project-slug>.sqlite` and resides in the target repository root.
  - **External World (Graph)**: Acts as the primary read-only structural representation provided by `codebase-memory-mcp`.
- **Merging Logic**: During `library sync`, the Librarian automatically merges data from both sources, prioritizing the "Mind" for internal state and the "Graph" for structural definitions.


---
---

## Observability & Logging (`brain/logger.py`)

Quantum Brain uses `loguru` for structured logging. It supports both human-readable console output and machine-parsable JSON formatting for production environments.

- **Functions**: `get_logger()`, `configure_logging()`
- **Features**: Automatic module/line tracking, exception capturing, and environment-based level setting.

---

## Semantic Embeddings (`brain/embedder.py`)

Semantic matching and distance computations are powered by `sentence-transformers` using local resources.

- **Class**: `Embedder`
- **Model**: `all-MiniLM-L6-v2` (default, generates 384-dimensional dense vectors)
- **Methods**:
  - `embed(texts)`: Encodes single strings or lists of strings.
  - `cosine_similarity(v1, v2)`: Returns cosine similarity between two numpy vectors.
  - `semantic_distance(v1, v2)`: Returns `1.0 - cosine_similarity`.

---

## Environment Management (`uv`)

The project uses `uv` for fast dependency resolution and execution.

- **Sync**: `uv sync`
- **Run**: `uv run qbrain <command>`
- **Develop**: `uv add --dev pytest`

Dependencies are defined in `pyproject.toml` using standard PEP 621 fields.

