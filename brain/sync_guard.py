import os
import subprocess
import time
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from brain.persistence_manager import PersistenceManager
from brain.logger import get_logger

logger = get_logger(__name__)

@dataclass
class DriftEvent:
    tier: int         # 1=git, 2=mtime, 3=deep
    event_type: str   # MODIFIED|DELETED|NEW|TOMBSTONE|UNINDEXED|REBASE_DETECTED
    file_path: str
    detail: str
    drift_seconds: float
    severity: str     # INFO|WARN|CRITICAL

class SyncGuard:
    TRACKED_EXTENSIONS = {'.php', '.py', '.js', '.ts', '.go', '.rs', '.cpp', '.c', '.h'}

    def run_tier1(self, repo_path: str, last_commit: Optional[str]) -> List[DriftEvent]:
        """
        Git diff drift detection.
        Checks if last_commit is an ancestor of HEAD. If not, rebase or force push is detected.
        Otherwise, reads changed files via git diff.
        """
        if not last_commit:
            return []

        # 1. Merge-base ancestor check
        try:
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", last_commit, "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Merge-base check failed. Rebase or history rewrite detected: {e}")
            return [
                DriftEvent(
                    tier=1,
                    event_type="REBASE_DETECTED",
                    file_path="",
                    detail=f"Branch history diverged from last synced commit: {last_commit}",
                    drift_seconds=0.0,
                    severity="CRITICAL"
                )
            ]

        # 2. Get git diff changes
        events = []
        try:
            res = subprocess.run(
                ["git", "diff", "--name-status", f"{last_commit}..HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8"
            )
            output = res.stdout.strip()
            if not output:
                return []

            now = time.time()
            for line in output.splitlines():
                parts = line.strip().split("\t")
                if len(parts) < 2:
                    continue
                status_char = parts[0][0]
                file_path = parts[1].replace("\\", "/")
                
                _, ext = os.path.splitext(file_path.lower())
                if ext not in self.TRACKED_EXTENSIONS:
                    continue

                if status_char == "M":
                    event_type = "MODIFIED"
                    severity = "INFO"
                elif status_char == "D":
                    event_type = "DELETED"
                    severity = "WARN"
                elif status_char in ("A", "C", "R"):
                    event_type = "NEW"
                    severity = "INFO"
                else:
                    continue

                events.append(
                    DriftEvent(
                        tier=1,
                        event_type=event_type,
                        file_path=file_path,
                        detail=f"Git status: {parts[0]}",
                        drift_seconds=0.0,
                        severity=severity
                    )
                )
        except Exception as e:
            logger.error(f"Git diff failed: {e}")
            
        return events

    def run_tier2(self, repo_path: str, persistence: PersistenceManager) -> List[DriftEvent]:
        """
        Filesystem-level fast walk comparison.
        Compares disk (mtime/size) against SQLite manifest.
        """
        events = []
        now = time.time()
        
        try:
            manifest = persistence.load_manifest()
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            return []

        visited_paths: Set[str] = set()
        disk_files: Dict[str, tuple] = {}

        # 1. Walk directory and compare stats
        for root, _, files in os.walk(repo_path):
            # Skip hidden folders (e.g. .git, .qbrain)
            rel_root = os.path.relpath(root, repo_path)
            if rel_root != "." and any(part.startswith(".") for part in rel_root.split(os.sep)):
                continue
                
            for file in files:
                _, ext = os.path.splitext(file.lower())
                if ext not in self.TRACKED_EXTENSIONS:
                    continue

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")
                visited_paths.add(rel_path)

                try:
                    stat = os.stat(full_path)
                    mtime = stat.st_mtime
                    size = stat.st_size
                    disk_files[rel_path] = (mtime, size)
                    
                    if rel_path not in manifest:
                        events.append(
                            DriftEvent(
                                tier=2,
                                event_type="NEW",
                                file_path=rel_path,
                                detail=f"New file found on disk (size: {size} bytes)",
                                drift_seconds=0.0,
                                severity="INFO"
                            )
                        )
                    else:
                        m_mtime, m_size = manifest[rel_path]
                        # Handle mtime skew and changes
                        if mtime != m_mtime or size != m_size:
                            events.append(
                                DriftEvent(
                                    tier=2,
                                    event_type="MODIFIED",
                                    file_path=rel_path,
                                    detail=f"Modified (size: {m_size} -> {size}, mtime: {m_mtime} -> {mtime})",
                                    drift_seconds=abs(mtime - m_mtime),
                                    severity="INFO"
                                )
                            )
                except Exception as e:
                    logger.warn(f"Failed to stat file {full_path}: {e}")

        # 2. Check for deleted files (in manifest, but not visited on disk)
        for rel_path in manifest.keys():
            if rel_path not in visited_paths:
                events.append(
                    DriftEvent(
                        tier=2,
                        event_type="DELETED",
                        file_path=rel_path,
                        detail="File deleted from disk",
                        drift_seconds=0.0,
                        severity="WARN"
                    )
                )
                try:
                    persistence.mark_tombstone(rel_path)
                except Exception as e:
                    logger.error(f"Failed to mark tombstone for {rel_path}: {e}")

        # 3. Update manifest table with the current snapshot of files on disk
        if disk_files:
            try:
                persistence.save_manifest_snapshot(disk_files)
            except Exception as e:
                logger.error(f"Failed to save manifest snapshot: {e}")

        return events

    def run_tier3(self, repo_path: str, indexer: "Indexer") -> List[DriftEvent]:
        """
        Deep graph reconciliation (Tier 3).
        Queries all file paths referenced in the MCP graph and compares them against disk.
        """
        events = []
        try:
            # Query graph for files associated with symbols
            query = "MATCH (n) WHERE n:Function OR n:Method OR n:Module OR n:Class OR n:Interface OR n:Enum RETURN DISTINCT n.file_path AS file, n.file AS file_alt"
            raw_res = indexer.query_graph(query)
            
            graph_files = set()
            for r in raw_res:
                f_path = r.get("file") or r.get("file_alt")
                if f_path:
                    # Normalize path format
                    norm_path = f_path.replace("\\", "/").strip("/")
                    graph_files.add(norm_path)
        except Exception as e:
            logger.error(f"Failed to query graph files for Tier 3: {e}")
            return []

        # Walk disk to collect existing tracked files
        disk_files = set()
        for root, _, files in os.walk(repo_path):
            rel_root = os.path.relpath(root, repo_path)
            if rel_root != "." and any(part.startswith(".") for part in rel_root.split(os.sep)):
                continue
            for file in files:
                _, ext = os.path.splitext(file.lower())
                if ext in self.TRACKED_EXTENSIONS:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/").strip("/")
                    disk_files.add(rel_path)

        # 1. TOMBSTONES: In graph, but missing on disk
        for g_file in graph_files:
            if g_file not in disk_files:
                events.append(
                    DriftEvent(
                        tier=3,
                        event_type="TOMBSTONE",
                        file_path=g_file,
                        detail="File exists in the graph database but is missing from disk",
                        drift_seconds=0.0,
                        severity="WARN"
                    )
                )

        # 2. UNINDEXED: On disk, but missing in graph
        for d_file in disk_files:
            if d_file not in graph_files:
                events.append(
                    DriftEvent(
                        tier=3,
                        event_type="UNINDEXED",
                        file_path=d_file,
                        detail="File exists on disk but is not indexed in the graph database",
                        drift_seconds=0.0,
                        severity="INFO"
                    )
                )

        return events

    def should_trigger_repopulation(self, events: List[DriftEvent], total_files: int) -> bool:
        """
        Decision rule to trigger a selective repopulation of the Obsidian vault.
        Triggered if merge-base failed (REBASE_DETECTED) or tombstones exceed 20% of total files.
        """
        if any(e.event_type == "REBASE_DETECTED" for e in events):
            return True
            
        tombstone_or_deleted = {e.file_path for e in events if e.event_type in ("TOMBSTONE", "DELETED") and e.file_path}
        if total_files > 0 and (len(tombstone_or_deleted) / total_files) > 0.20:
            return True
            
        return False
