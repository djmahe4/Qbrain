import pytest
import os
import json
from brain.entrypoint_finder import EntrypointFinder

def test_find_entrypoint_package_json(tmp_path):
    # Setup package.json
    pkg_data = {
        "name": "my-app",
        "version": "1.0.0",
        "main": "src/index.js",
        "bin": {
            "my-cli": "bin/cli.js"
        }
    }
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text(json.dumps(pkg_data))

    finder = EntrypointFinder(str(tmp_path))
    entrypoints = finder.find_entrypoints()

    # Should find main and bin entrypoints
    files = [e["file"] for e in entrypoints]
    assert "src/index.js" in files
    assert "bin/cli.js" in files
    assert any(e["name"] == "main" for e in entrypoints)
    assert any(e["name"] == "my-cli" for e in entrypoints)

def test_find_entrypoint_cargo_toml(tmp_path):
    cargo_data = """
[package]
name = "my-rust-app"
version = "0.1.0"

[[bin]]
name = "server"
path = "src/bin/server.rs"

[lib]
path = "src/lib.rs"
"""
    cargo_file = tmp_path / "Cargo.toml"
    cargo_file.write_text(cargo_data)

    finder = EntrypointFinder(str(tmp_path))
    entrypoints = finder.find_entrypoints()

    files = [e["file"] for e in entrypoints]
    assert "src/bin/server.rs" in files
    assert "src/lib.rs" in files
    assert any(e["name"] == "server" for e in entrypoints)
    assert any(e["name"] == "lib" for e in entrypoints)

def test_find_entrypoint_pyproject_toml(tmp_path):
    pyproject_data = """
[project]
name = "my-python-app"

[project.scripts]
run-app = "app.main:run"

[tool.poetry.scripts]
poetry-run = "app.poetry:main"
"""
    pyproject_file = tmp_path / "pyproject.toml"
    pyproject_file.write_text(pyproject_data)

    finder = EntrypointFinder(str(tmp_path))
    entrypoints = finder.find_entrypoints()

    assert len(entrypoints) == 2
    names = [e["name"] for e in entrypoints]
    assert "run-app" in names
    assert "poetry-run" in names

def test_find_entrypoint_yaml_config(tmp_path):
    yaml_data = """
entrypoint: src/main.cpp
app:
  entrypoint: app.py
"""
    yaml_file = tmp_path / "app.yaml"
    yaml_file.write_text(yaml_data)

    finder = EntrypointFinder(str(tmp_path))
    entrypoints = finder.find_entrypoints()

    files = [e["file"] for e in entrypoints]
    assert "src/main.cpp" in files or "app.py" in files

def test_find_entrypoint_fallback(tmp_path):
    # Test directory fallback when no configs exist
    # Create index.ts
    os.makedirs(tmp_path / "src", exist_ok=True)
    index_file = tmp_path / "src" / "index.ts"
    index_file.write_text("// entrypoint code")

    # Create main.cpp
    main_file = tmp_path / "main.cpp"
    main_file.write_text("// main function")

    finder = EntrypointFinder(str(tmp_path))
    entrypoints = finder.find_entrypoints()

    files = [e["file"] for e in entrypoints]
    assert "src/index.ts" in files
    assert "main.cpp" in files

def test_find_entrypoint_empty(tmp_path):
    finder = EntrypointFinder(str(tmp_path))
    entrypoints = finder.find_entrypoints()
    assert entrypoints == []
