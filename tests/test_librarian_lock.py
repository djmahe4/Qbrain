import pytest
import os
import time
import threading
import tempfile
from brain.librarian import LibrarianEngine

def test_librarian_lock_retry():
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = os.path.abspath(tmp_dir)
        vault_path = os.path.join(repo_path, "vault")
        engine = LibrarianEngine(repo_path, vault_path)
        
        # Use a subprocess to hold the lock
        import subprocess
        import sys
        
        # Need to ensure brain is in sys.path for the subprocess
        cwd = os.getcwd()
        code = f"""
import time
import os
import sys
sys.path.append({cwd!r})
from brain.librarian import LibrarianEngine
engine = LibrarianEngine({repo_path!r}, {vault_path!r})
with engine.lock(timeout=1):
    time.sleep(2)
"""
        proc = subprocess.Popen([sys.executable, "-c", code])
        
        time.sleep(1.0) # Give it time to acquire
        
        # This should wait and eventually succeed after the subprocess exits
        start = time.time()
        with engine.lock(timeout=10):
            duration = time.time() - start
            assert duration >= 0.5
            
        proc.wait()
def test_librarian_lock_timeout():
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = os.path.abspath(tmp_dir)
        vault_path = os.path.join(repo_path, "vault")
        engine = LibrarianEngine(repo_path, vault_path)
        
        # Manually write a lock file with current PID
        with open(engine.lock_file, "w") as f:
            f.write(str(os.getpid()))
            
        # This should fail because PID is running and we are trying to acquire it again 
        # (even if it is our own PID, the current implementation treats it as 'busy')
        with pytest.raises(RuntimeError) as excinfo:
            with engine.lock(timeout=1, retry_interval=0.1):
                pass
        assert "locked by a running process" in str(excinfo.value)
