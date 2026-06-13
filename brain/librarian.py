import os
from contextlib import contextmanager
import yaml
import time

class LibrarianEngine:
    def __init__(self, repo_path: str, vault_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self.vault_path = os.path.abspath(vault_path)
        self.lock_file = os.path.join(self.repo_path, ".qbrain.lock")

    def _safe_path(self, *parts: str) -> str:
        """Ensure the resulting path is within the vault_path to prevent traversal."""
        full_path = os.path.abspath(os.path.join(self.vault_path, *parts))
        if not full_path.startswith(self.vault_path):
            raise ValueError(f"Security Risk: Path traversal detected! {full_path} is outside {self.vault_path}")
        return full_path

    def setup_vault(self):
        os.makedirs(self._safe_path("symbols"), exist_ok=True)
        os.makedirs(self._safe_path("files"), exist_ok=True)
        os.makedirs(self._safe_path("behaviors"), exist_ok=True)
        os.makedirs(self._safe_path("changes", "recent"), exist_ok=True)
        os.makedirs(self._safe_path("changes", "archive"), exist_ok=True)
        os.makedirs(self._safe_path("rules"), exist_ok=True)
        
        baseline_file = self._safe_path("baseline.md")
        if not os.path.exists(baseline_file):
            with open(baseline_file, "w", encoding="utf-8") as f:
                f.write("# Baseline Snapshot\n\nThis is the initial snapshot of the repository state.")

    @contextmanager
    def lock(self, timeout: int = 30, retry_interval: float = 0.5):
        """
        Context manager for acquiring a process-level lock.
        Waits up to 'timeout' seconds.
        """
        start_time = time.time()
        acquired = False
        busy = True
        while time.time() - start_time < timeout:
            if os.path.exists(self.lock_file):
                try:
                    with open(self.lock_file, "r") as f:
                        pid_str = f.read().strip()
                        if pid_str:
                            pid = int(pid_str)
                            if not self._is_pid_running(pid):
                                busy = False
                                break
                        else:
                            busy = False
                            break
                except (ValueError, OSError):
                    busy = False
                    break
                
                time.sleep(retry_interval)
            else:
                busy = False
                break

        if busy:
             raise RuntimeError(f"Database/repository is locked by a running process on {self.lock_file} (timeout after {timeout} seconds).")

        try:
            # Use 'x' for atomicity if possible
            with open(self.lock_file, "x") as f:
                f.write(str(os.getpid()))
            acquired = True
        except FileExistsError:
            # Check if stale again (race condition)
            try:
                with open(self.lock_file, "r") as f:
                    pid = int(f.read().strip())
                if not self._is_pid_running(pid):
                    with open(self.lock_file, "w") as f:
                        f.write(str(os.getpid()))
                    acquired = True
            except (ValueError, OSError):
                pass
        except OSError as e:
             raise RuntimeError(f"Failed to create lock file {self.lock_file}: {e}")

        if not acquired:
             raise RuntimeError(f"Could not acquire lock on {self.lock_file} within {timeout} seconds (race condition).")



        try:
            yield
        finally:
            if os.path.exists(self.lock_file):
                try:
                    os.remove(self.lock_file)
                except OSError:
                    pass

    def _is_pid_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            # Under Windows or Unix, this checks if process is running
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            # Fallback
            if os.name == 'nt':
                # Windows tasklist fallback
                import subprocess
                try:
                    out = subprocess.check_output(
                        ["tasklist", "/FI", f"PID eq {pid}"], 
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    return str(pid).encode() in out
                except Exception:
                    return True  # Safe fallback to prevent concurrency
            else:
                try:
                    os.kill(pid, 0)
                    return True
                except OSError:
                    return False

    def export_symbol(self, symbol_data: dict):
        name = symbol_data.get("name")
        if not name:
            return
        
        frontmatter = {
            "type": "symbol",
            "name": name,
            "language": symbol_data.get("language"),
            "file": symbol_data.get("file"),
            "signature": symbol_data.get("signature")
        }
        
        filepath = self._safe_path("symbols", f"{name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(frontmatter, f, default_flow_style=False)
            f.write("---\n\n")
            f.write(f"# Symbol: {name}\n\n")
            if symbol_data.get("docstring"):
                f.write(f"## Documentation\n{symbol_data.get('docstring')}\n\n")
            if symbol_data.get("params"):
                f.write("## Parameters\n")
                for param in symbol_data.get("params", []):
                    f.write(f"- `{param.get('name')}` ({param.get('type')}): {param.get('description', '')}\n")
                f.write("\n")
            if symbol_data.get("returns"):
                ret = symbol_data.get("returns")
                f.write(f"## Returns\n`{ret.get('type')}`: {ret.get('description', '')}\n\n")
            if symbol_data.get("business_rules"):
                f.write("## Business Rules\n")
                for rule in symbol_data.get("business_rules", []):
                    f.write(f"- {rule}\n")

    def export_behavior(self, behavior_data: dict):
        name = behavior_data.get("name")
        if not name:
            return
        
        frontmatter = {
            "type": "behavior",
            "name": name,
            "states": behavior_data.get("states", [])
        }
        
        filepath = self._safe_path("behaviors", f"{name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("---\n")
            yaml.safe_dump(frontmatter, f, default_flow_style=False)
            f.write("---\n\n")
            f.write(f"# Behavior: {name}\n\n")
            
            # State machine rendering
            f.write("## State Machine\n\n")
            f.write("```mermaid\n")
            f.write("stateDiagram-v2\n")
            
            states = behavior_data.get("states", [])
            for state in states:
                f.write(f"    {state}\n")
            
            transitions = behavior_data.get("transitions", [])
            for t in transitions:
                frm = t.get("from")
                to = t.get("to")
                cond = t.get("condition")
                if cond:
                    f.write(f"    {frm} --> {to}: {cond}\n")
                else:
                    f.write(f"    {frm} --> {to}\n")
            
            f.write("```\n")

    def export_warnings(self, warnings_list: list):
        filepath = self._safe_path("rules", "warnings.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# Docstring & Quality Invariants Warnings\n\n")
            if not warnings_list:
                f.write("✅ No docstring or quality warning violations detected.\n")
                return
            
            f.write("The following functions or methods violate quality invariants (missing or malformed docstrings):\n\n")
            f.write("| Symbol | File | Issue |\n")
            f.write("| :--- | :--- | :--- |\n")
            for w in warnings_list:
                issues_str = ", ".join(w.get("warnings", []))
                f.write(f"| `[[{w.get('name')}]]` | `{w.get('file')}` | {issues_str} |\n")
