import os
import time
import pytest
import numpy as np
from unittest.mock import MagicMock
from brain.config import Config
from brain.rag.retriever import VaultRetriever

class MockEmbedder:
    """Mock embedder that returns deterministic vectors based on text content."""
    def embed(self, text):
        if isinstance(text, list):
            return np.array([self._vectorize(t) for t in text])
        return self._vectorize(text)

    def _vectorize(self, text):
        vec = np.zeros(8)
        t_low = text.lower()
        if "upload" in t_low or "image" in t_low:
            vec[0] = 1.0
        if "sql" in t_low or "query" in t_low:
            vec[1] = 1.0
        if "sanitize" in t_low or "filter" in t_low:
            vec[2] = 1.0
        
        vec[4] = (len(text) % 10) / 10.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def cosine_similarity(self, v1, v2):
        return float(np.dot(v1, v2))

@pytest.fixture
def realistic_mismatch_vault(tmp_path):
    vault_dir = tmp_path / "obsidian_vault"
    os.makedirs(vault_dir / "files", exist_ok=True)
    os.makedirs(vault_dir / "behaviors", exist_ok=True)

    # File 1: Legacy Upload (Vulnerable - TAINTED)
    # Comment claims it only allows images, but dataflow shows it is TAINTED
    upload_legacy = """---
archetype: file-uploader
winner: TAINTED
---
# File: vulnerabilities/upload/source/low.php

## Description
Handles user profile picture uploads.
Comment: "Only allows safe image uploads."

## Dynamic Variable Tracking
| Variable | Source | State |
| :--- | :--- | :--- |
| `$target_file` | `_FILES` | `TAINTED` |
"""
    
    # File 2: Modern Upload (Secure - SAFE)
    # Comment also claims it only allows images, and dataflow confirms it is SAFE
    upload_modern = """---
archetype: file-uploader
winner: SAFE
---
# File: vulnerabilities/upload/source/impossible.php

## Description
Handles user profile picture uploads with strict extension validation.
Comment: "Only allows safe image uploads."

## Dynamic Variable Tracking
| Variable | Source | State |
| :--- | :--- | :--- |
| `$target_file` | `_FILES` | `SAFE` |
"""

    # File 3: API Upload (Vulnerable - TAINTED)
    # Redundant comment again, but dataflow is TAINTED
    upload_api = """---
archetype: file-uploader
winner: TAINTED
---
# File: vulnerabilities/api/upload.php

## Description
Endpoint for mobile API avatar uploads.
Comment: "Only allows safe image uploads."

## Dynamic Variable Tracking
| Variable | Source | State |
| :--- | :--- | :--- |
| `$uploaded_path` | `_FILES` | `TAINTED` |
"""

    with open(vault_dir / "files" / "vulnerabilities_upload_source_low_php.md", "w", encoding="utf-8") as f:
        f.write(upload_legacy)
    with open(vault_dir / "files" / "vulnerabilities_upload_source_impossible_php.md", "w", encoding="utf-8") as f:
        f.write(upload_modern)
    with open(vault_dir / "files" / "vulnerabilities_api_upload_php.md", "w", encoding="utf-8") as f:
        f.write(upload_api)

    # Add 100 dummy files to simulate a large varied repository context
    for i in range(100):
        category = ["files", "behaviors"][i % 2]
        filename = f"other_note_{i}.md"
        content = f"""# Other Note {i}
This is a dummy note in {category}.
It discusses sql database queries.
Archetype: database-helper
"""
        with open(vault_dir / category / filename, "w", encoding="utf-8") as f:
            f.write(content)

    return vault_dir

def test_retriever_redundancy_and_mismatch_detection(realistic_mismatch_vault):
    """
    Stress test the retriever's ability to fetch context that allows the brain
    to identify redundant comments and code-logic mismatches (intent flips).
    """
    config = MagicMock()
    config.vault_path = str(realistic_mismatch_vault)
    embedder = MockEmbedder()
    
    retriever = VaultRetriever(config, embedder)
    
    # 1. Retrieve notes related to "safe image uploads"
    results = retriever.retrieve("Only allows safe image uploads", top_k=10)
    
    # Verify that the three files containing the comment are at the top of the results
    upload_results = [r for r in results if "upload" in r["file_path"]]
    assert len(upload_results) == 3

    # 2. Simulate the Brain's reasoning over the retrieved context
    # A: Identify Redundant Comments
    comments_found = []
    for r in upload_results:
        # Extract the comment line from the content
        for line in r["content"].splitlines():
            if "Comment:" in line:
                comments_found.append(line.split(":", 1)[1].strip().strip('"'))
                
    # All 3 files contain the exact same comment text -> Redundancy!
    assert len(comments_found) == 3
    assert len(set(comments_found)) == 1
    assert comments_found[0] == "Only allows safe image uploads."

    # B: Identify Code-Logic Mismatches (Intent Flips)
    mismatches = []
    for idx, r in enumerate(upload_results):
        winner_state = r["metadata"].get("winner")
        file_path = r["file_path"]
        comment = comments_found[idx]
        
        # If the comment claims it is "safe", but the static analysis winner is TAINTED,
        # we have a code-logic mismatch!
        if "safe" in comment.lower() and winner_state == "TAINTED":
            mismatches.append({
                "file_path": file_path,
                "comment": comment,
                "actual_state": winner_state,
                "mismatch_type": "Intent Flip (Lying Comment)",
                "description": f"Comment claims: '{comment}' but the static analysis winner is '{winner_state}' (vulnerable)."
            })

    # The brain successfully identifies that 2 out of the 3 upload files have a code-logic mismatch
    assert len(mismatches) == 2
    assert any("low_php" in m["file_path"] for m in mismatches)
    assert any("api_upload" in m["file_path"] for m in mismatches)
    # The impossible.php file is secure (SAFE), so it should NOT be in the mismatches list
    assert not any("impossible_php" in m["file_path"] for m in mismatches)

    print("\nSuccessfully identified redundant comments across 3 files.")
    print("\n--- CODE-LOGIC MISMATCH DIAGNOSTICS ---")
    for m in mismatches:
        print(f"File: {m['file_path']}")
        print(f"  Type: {m['mismatch_type']}")
        print(f"  {m['description']}")

