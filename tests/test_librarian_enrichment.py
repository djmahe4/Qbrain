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
        "archetype": "calculation-engine",
        "mass": 4.5,
        "potential_energy": 12.0,
        "code_snippet": "def calculateTrajectory(velocity, angle):\n    g = 9.81\n    return (velocity * math.cos(angle), velocity * math.sin(angle) - 0.5 * g)\n",
        "semantic_neighbors": [("physics/trajectory.py:simulateOrbit", 0.95), ("physics/trajectory.py:getGravityField", 0.88)],
        "callers": ["physics/trajectory.py:runSimulation", "physics/trajectory.py:main"],
        "callees": ["physics/trajectory.py:math.cos", "physics/trajectory.py:math.sin"]
    }


    file_data = {
        "file_path": "physics/trajectory.py",
        "language": "python",
        "lines_of_code": 10,
        "size_bytes": 500,
        "symbols_data": [symbol_data]
    }

    engine.export_file(file_data)
    file_doc = vault_path / "files" / "physics_trajectory_py.md"
    assert os.path.exists(file_doc)

    with open(file_doc, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify Sections
    assert "#### Implementation" in content
    assert "```python" in content
    assert "def calculateTrajectory" in content
    assert "g = 9.81" in content

    assert "#### Entanglements" in content
    assert "##### Inbound Callers" in content
    assert "physics_trajectory_py#Symbol: runSimulation" in content
    assert "physics_trajectory_py#Symbol: main" in content
    assert "##### Outbound Callees" in content
    assert "physics_trajectory_py#Symbol: math.cos" in content
    assert "physics_trajectory_py#Symbol: math.sin" in content


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

    assert "# 🛡️ Security Vulnerability Report" in content
    assert "| Severity | Symbol | File | Finding |" in content
    assert "files/auth_py#Symbol: login" in content
    assert "CRITICAL" in content
    assert "files/utils_py#Symbol: exec_cmd" in content
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
    assert "files/data_py#Symbol: processData" in content
    assert "data.py" in content
    assert "25.0" in content
 
    assert "## ⚡ Attention Hotspots (Highest Drift / Attention Debt)" in content
    assert "files/jobs_py#Symbol: runJob" in content
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
    assert "files/physics_trajectory_py#Symbol: calculateTrajectory" in content
    assert "files/physics_orbit_py#Symbol: simulateOrbit" in content
    assert "## Data-Model" in content
    assert "files/models_user_py#Symbol: UserModel" in content


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
    assert "files/physics_trajectory_py\\|physics/trajectory.py" in content
    assert "files/models_user_py\\|models/user.py" in content


def test_librarian_enrichment_symbol_line_number(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    symbol_data = {
        "name": "calculateTrajectory",
        "language": "python",
        "file": "physics/trajectory.py",
        "signature": "def calculateTrajectory(velocity, angle)",
        "line": 42,
        "line_range": [42, 45]
    }

    file_data = {
        "file_path": "physics/trajectory.py",
        "language": "python",
        "lines_of_code": 120,
        "size_bytes": 4096,
        "symbols_data": [symbol_data]
    }

    engine.export_file(file_data)
    file_doc = vault_path / "files" / "physics_trajectory_py.md"
    assert os.path.exists(file_doc)

    with open(file_doc, "r", encoding="utf-8") as f:
        content = f.read()

    assert "- **Line:** 42" in content


def test_librarian_enrichment_export_file(tmp_path):
    vault_path = tmp_path / "obsidian_vault"
    engine = LibrarianEngine(str(tmp_path), str(vault_path))
    engine.setup_vault()

    file_data = {
        "file_path": "physics/trajectory.py",
        "language": "python",
        "lines_of_code": 120,
        "size_bytes": 4096,
        "symbols_data": [
            {"name": "calculateTrajectory", "kind": "Function", "line": 10},
            {"name": "simulateOrbit", "kind": "Function", "line": 25}
        ]
    }

    engine.export_file(file_data)
    file_doc = vault_path / "files" / "physics_trajectory_py.md"
    assert os.path.exists(file_doc)

    with open(file_doc, "r", encoding="utf-8") as f:
        content = f.read()

    assert "# File: physics/trajectory.py" in content
    assert "## Metadata" in content
    assert "- **Language:** python" in content
    assert "- **Lines of Code:** 120" in content
    assert "- **Size:** 4096 bytes" in content
    assert "## Symbols Index" in content
    assert "[[#Symbol: calculateTrajectory\\|calculateTrajectory]]" in content
    assert "[[#Symbol: simulateOrbit\\|simulateOrbit]]" in content

