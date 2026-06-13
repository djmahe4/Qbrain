# quant-blm Git Watcher & Branch Diff Documentation

This document describes the branch delta and cron watcher integration implemented in Phase 4 of the **Quantum Brain** (`quant-blm`).

## 1. Branch Difference Engine (`brain/branch_diff.py`)

Handles listing and embedding comparison between branch heads:
- **Unique File Delta**: Computes `X - Y` and `Y - X` using `git ls-tree` sets.
- **Added Files Meanings**: Resolves file definitions of new elements, providing short extracts representing "meaning".
- **Semantic Drift on Common Code**: Compares corresponding common source files across branches, embeds them, and flags files with `semantic_distance > semantic_drift_threshold`.

## 2. APScheduler Watcher Cron (`brain/git_watcher.py`)

A background job runner designed to run continually and monitor file alterations:
- **Change Detection**: Leverages `detect_changes` on the memory graph.
- **Re-Scoring Pipeline**: Once changes are captured, it fetches all codebase symbols, extracts genomes, runs the N-body simulation, and uploads results back to `codebase-memory-mcp`.
- **Commit Checkpoint**: Persists last processed hash and check timestamp in `.quantum-brain-state.json`.
- **Logging**: Uses `loguru` to report scan status and simulation updates.

