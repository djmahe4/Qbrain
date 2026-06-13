import os
import json
import time
import shutil
from typing import Dict, Any, Optional
from apscheduler.schedulers.blocking import BlockingScheduler
from brain.config import Config
from brain.indexer import Indexer
from brain.embedder import Embedder
from brain.quantum_scorer import QuantumScorer, FunctionNode
from brain.docstring_parser import DocstringParser
from brain.dependency_mapper import DependencyMapper

class GitWatcher:
    def __init__(self, config: Config, indexer: Indexer, scorer: QuantumScorer, embedder: Embedder):
        self.config = config
        self.indexer = indexer
        self.scorer = scorer
        self.embedder = embedder
        self.state_file = os.path.join(config.repo_path, ".quantum-brain-state.json")
        self.scheduler = BlockingScheduler()

    def get_last_processed_commit(self) -> str:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    return data.get("last_commit", "")
            except Exception:
                pass
        return ""

    def save_last_processed_commit(self, commit_hash: str):
        try:
            with open(self.state_file, "w") as f:
                json.dump({"last_commit": commit_hash, "timestamp": time.time()}, f)
        except Exception:
            pass

    def check_diff(self):
        """
        Check for semantic changes in the codebase.
        """
        print("[Cron] Checking for semantic updates via codebase-memory-mcp...")
        try:
            # 1. Run detect_changes
            changes = self.indexer.detect_changes()
            modified = changes.get("modified_files", [])
            affected_symbols = changes.get("affected_symbols", [])

            if not modified:
                print("[Cron] No file changes detected.")
                return

            print(f"[Cron] Detected changes in files: {modified}")
            print(f"[Cron] Affected symbols to re-evaluate: {[s.get('name') for s in affected_symbols]}")

            # 2. Extract and re-embed docstrings
            parser = DocstringParser(self.indexer)
            funcs = parser.get_functions_with_docstrings()

            nodes = []
            for f in funcs:
                genome = parser.build_genome(f)
                emb = self.embedder.embed(genome)
                node = FunctionNode(
                    name=f.get("name", ""),
                    embedding=emb,
                    complexity=float(f.get("complexity", 1.0) or 1.0),
                    side_effects=float(f.get("sideEffects", 0.0) or 0.0),
                    is_exported=bool(f.get("isExported", False)),
                    file=f.get("file", ""),
                    line=int(f.get("line", 0) or 0)
                )
                nodes.append(node)

            # 3. Re-run scoring simulation
            print("[Cron] Re-running N-body gravitational simulation...")
            self.scorer.run_simulation(nodes)
            self.scorer.write_physics_to_graph(nodes)

            # 4. Run dependency mapping
            try:
                dep_mapper = DependencyMapper(self.indexer)
                deps = dep_mapper.get_dependencies()
                dep_mapper.write_to_graph(deps)
                print(f"[Cron] Dependency graph updated: {len(deps)} dependency edges.")
            except Exception as dep_err:
                print(f"[Cron] Warning: dependency mapping failed: {dep_err}")

            # 5. Save state
            # Resolve git binary safely to avoid shell injection
            import subprocess
            git_bin = shutil.which("git") or "git"
            try:
                commit_hash = subprocess.check_output(
                    [git_bin, "rev-parse", "HEAD"],
                    cwd=self.config.repo_path,
                    text=True
                ).strip()
                self.save_last_processed_commit(commit_hash)
            except Exception:
                pass

            print("[Cron] Codebase physics updated successfully.")

        except Exception as e:
            print(f"[Cron] Error checking semantic changes: {e}")

    def sync_branch_lru(self):
        """Periodic job: re-run dependency mapping to keep the LRU cache warm."""
        print("[Cron/LRU] Running branch LRU dependency sync...")
        try:
            dep_mapper = DependencyMapper(self.indexer)
            deps = dep_mapper.get_dependencies()
            dep_mapper.write_to_graph(deps)
            print(f"[Cron/LRU] Synced {len(deps)} dependency edges.")
        except Exception as e:
            print(f"[Cron/LRU] LRU sync failed: {e}")

    def start(self):
        diff_interval = self.config.cron_config.get("git_diff_check_interval_minutes", 5)
        lru_interval = self.config.cron_config.get("branch_lru_sync_interval_minutes", 15)

        # Job 1: git diff + physics update
        self.scheduler.add_job(
            self.check_diff,
            "interval",
            minutes=diff_interval,
            next_run_time=None  # do not auto-fire at startup; we call manually below
        )

        # Job 2: LRU branch sync (uses branch_lru_sync_interval_minutes from config)
        self.scheduler.add_job(
            self.sync_branch_lru,
            "interval",
            minutes=lru_interval,
            next_run_time=None
        )

        print(f"Starting Quantum Brain Watcher Cron "
              f"(diff interval: {diff_interval}m, lru sync interval: {lru_interval}m)...")

        # Trigger an initial check immediately
        self.check_diff()
        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("Stopping Watcher Cron.")
