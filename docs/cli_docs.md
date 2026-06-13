# quant-blm CLI Documentation

This document describes the CLI user interface implemented in Phase 5 of the **Quantum Brain** (`quant-blm`).

## 1. CLI Entry Point (`brain/cli.py`)

The CLI is managed using `uv` and implemented with `typer`.

### Execution
To run any command:
```bash
uv run qbrain <command> [args]
```

### Command Structure
The CLI logic is modularized into `brain/commands/` for better maintainability:
- `index.py`: Repository indexing.
- `monitor.py`: Watcher and scoring.
- `query.py`: Search and diff.
- `library.py`: Obsidian sync.

### Available Commands



- **`qbrain index [path]`**: Runs manual project code parsing.
- **`qbrain watch [--interval X]`**: Runs the in-process cron monitor checking git diffs every `X` minutes.
- **`qbrain score [--top K]`**: Executes N-body gravity calculations, writes scores to the DB, and shows top `K` results.
- **`qbrain diff --base Y --head X`**: Analyzes git branch files and identifies semantic drifts.
- **`qbrain docstrings --query "text"`**: Runs a vector search over function docstrings using local cosine similarity scores.
- **`qbrain status`**: Shows configuration stats and the last processed commit hash.
- **`qbrain entangled --function name`**: Finds functions strongly bound to the target function (forces > 0.5).
- **`qbrain calibrate`**: Automatically finds optimized values for gravity `G` and repulsion `k_repulse` to hit ideal state distributions.
- **`qbrain deps`**: Queries and displays the dependency map (external imports, internal imports, and API calls) from the codebase-memory-mcp graph.
- **`qbrain rules [--top N]`**: Extracts and displays business logic rules categorized by type from function docstrings.
- **`qbrain entrypoints`**: Locates and lists main codebase entrypoints by parsing configurations (package.json, Cargo.toml, pyproject.toml, YAML) or falling back to a source file scan.
- **`qbrain projects`**: Lists all indexed projects in the centralized registry and checks whether their local Obsidian vault directories are initialized and configured.
- **`qbrain library sync`**: Synchronizes the codebase memory graph symbols and behavioral flow models directly to the local Obsidian vault, using PID-based lock protection to avoid background collisions.

