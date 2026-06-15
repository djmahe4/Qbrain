import pytest
import os
import yaml
from brain.librarian import LibrarianEngine

def test_librarian_enrichment_export_symbol(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    symbol_data = {
        "name": "calculateTrajectory",
        "language": "python",
        "file": "physics/trajectory.py",
        "signature": "def calculateTrajectory(velocity, angle)",
        "docstring": "Calculates projectile trajectory.",
        "params": [
            {"name": "velocity", "type": "float", "description": "initial velocity"},
            {"name": "angle", "type": "float", "description": "launch angle"}
        ],
        "returns": {"type": "tuple", "description": "x and y coordinates"},
        "business_rules": ["Uses gravity constant", "Handles air resistance"],
        # Enrichment fields:
        "archetype": "calculation-engine",
        "mass": 4.5,
        "potential_energy": 12.0,
        "code_snippet": "def calculateTrajectory(velocity, angle):\n    g = 9.81\n    return (velocity * math.cos(angle), velocity * math.sin(angle) - 0.5 * g)\n",
        "semantic_neighbors": [("simulateOrbit", 0.95), ("getGravityField", 0.88)],
        "callers": ["runSimulation", "main"],
        "callees": ["math.cos", "math.sin"]
    }

    engine.export_symbol(symbol_data)
    symbol_file = vault_path / "symbols" / "calculateTrajectory.md"
    assert os.path.exists(symbol_file)

    with open(symbol_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify Frontmatter YAML
    assert content.startswith("---")
    parts = content.split("---")
    assert len(parts) >= 3
    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter.get("archetype") == "calculation-engine"
    assert frontmatter.get("mass") == 4.5
    assert frontmatter.get("potential_energy") == 12.0

    # Verify Sections
    assert "## Implementation" in content
    assert "```python" in content
    assert "def calculateTrajectory" in content
    assert "g = 9.81" in content

    assert "## Semantic Neighbors" in content
    assert "[[simulateOrbit]]" in content
    assert "95.0% similarity" in content
    assert "[[getGravityField]]" in content
    assert "88.0% similarity" in content

    assert "## Entanglements" in content
    assert "### Inbound Callers" in content
    assert "[[runSimulation]]" in content
    assert "[[main]]" in content
    assert "### Outbound Callees" in content
    assert "[[math.cos]]" in content
    assert "[[math.sin]]" in content


def test_librarian_enrichment_export_vulnerabilities(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    vulnerabilities = [
        {
            "name": "login",
            "file": "auth.py",
            "severity": "CRITICAL",
            "message": "CWE-287: Improper Authentication - Hardcoded password"
        },
        {
            "name": "exec_cmd",
            "file": "utils.py",
            "severity": "HIGH",
            "message": "CWE-78: OS Command Injection - system execution"
        }
    ]

    engine.export_vulnerabilities(vulnerabilities)
    vuln_file = vault_path / "rules" / "vulnerabilities.md"
    assert os.path.exists(vuln_file)

    with open(vuln_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# 🛡️ Codebase Security Vulnerabilities" in content
    assert "| Severity | Symbol | File | Finding |" in content
    assert "[[login]]" in content
    assert "CRITICAL" in content
    assert "[[exec_cmd]]" in content
    assert "HIGH" in content


def test_librarian_enrichment_export_hotspots(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    hotspots = {
        "complexity": [
            {"name": "processData", "file": "data.py", "mass": 25.0, "archetype": "processor"},
            {"name": "parseToken", "file": "auth.py", "mass": 18.0, "archetype": "validator"}
        ],
        "attention": [
            {"name": "runJob", "file": "jobs.py", "potential_energy": 0.95, "archetype": "runner"},
            {"name": "processData", "file": "data.py", "potential_energy": 0.88, "archetype": "processor"}
        ]
    }

    engine.export_hotspots(hotspots)
    hotspots_file = vault_path / "rules" / "hotspots.md"
    assert os.path.exists(hotspots_file)

    with open(hotspots_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# 📊 Codebase Cognitive & Complexity Hotspots" in content
    assert "## 🏋️ Complexity Hotspots (Highest Mass)" in content
    assert "[[processData]]" in content
    assert "data.py" in content
    assert "25.0" in content

    assert "## ⚡ Attention Hotspots (Highest Drift / Attention Debt)" in content
    assert "[[runJob]]" in content
    assert "0.95" in content


def test_librarian_enrichment_export_archetypes(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    archetype_groups = {
        "calculation-engine": [
            {"name": "calculateTrajectory", "file": "physics/trajectory.py", "mass": 4.5, "confidence": 0.9},
            {"name": "simulateOrbit", "file": "physics/orbit.py", "mass": 6.2, "confidence": 0.85}
        ],
        "data-model": [
            {"name": "UserModel", "file": "models/user.py", "mass": 1.2, "confidence": 0.95}
        ]
    }

    engine.export_archetypes(archetype_groups)
    archetypes_file = vault_path / "rules" / "archetypes.md"
    assert os.path.exists(archetypes_file)

    with open(archetypes_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# 🧩 Codebase Semantic Archetypes" in content
    assert "## Calculation-Engine" in content
    assert "[[calculateTrajectory]]" in content
    assert "[[simulateOrbit]]" in content
    assert "## Data-Model" in content
    assert "[[UserModel]]" in content


def test_librarian_enrichment_export_branch_diff(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    diff_data = {
        "target_branch": "main",
        "semantic_distance": 0.125,
        "files": [
            {"file": "physics/trajectory.py", "status": "modified", "churn": 3, "relevance_score": 8.5},
            {"file": "models/user.py", "status": "added", "churn": 1, "relevance_score": 5.0}
        ]
    }

    engine.export_branch_diff(diff_data)
    diff_file = vault_path / "changes" / "branch_diff.md"
    assert os.path.exists(diff_file)

    with open(diff_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# 🌿 Branch Diff & Semantic Distance Report" in content
    assert "**Comparing current workspace against:** `main`" in content
    assert "**Semantic Distance:** `0.125`" in content
    assert "## 📝 Modified Files & Relevance Scores" in content
    assert "physics/trajectory.py" in content
    assert "models/user.py" in content
