# quant-blm Foundation Documentation

This document describes the foundation modules implemented in Phase 1 of the **Quantum Brain** (`quant-blm`).

## Architecture & Configuration

The foundation relies on a central configuration module (`brain/config.py`) which reads `.quantum-brain.json` from the repository root.

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

---

## Semantic Embeddings (`brain/embedder.py`)

Semantic matching and distance computations are powered by sentence-transformers using local resources (no external cloud requests).

- **Class**: `Embedder`
- **Model**: `all-MiniLM-L6-v2` (default, generates 384-dimensional dense vectors)
- **Methods**:
  - `embed(texts)`: Encodes single strings or lists of strings.
  - `cosine_similarity(v1, v2)`: Returns cosine similarity between two numpy vectors.
  - `semantic_distance(v1, v2)`: Returns `1.0 - cosine_similarity`.
