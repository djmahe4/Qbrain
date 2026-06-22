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
