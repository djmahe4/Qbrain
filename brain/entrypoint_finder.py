import os
import json
import re
from typing import Dict, List

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # pip install tomli
    except ImportError:
        tomllib = None  # pyproject.toml parsing disabled gracefully

try:
    import yaml
except ImportError:
    yaml = None


class EntrypointFinder:
    """
    Scans a repository to locate its main code entrypoints.
    Parses package.json, Cargo.toml, pyproject.toml, YAML files,
    and falls back to directory scanning for common entrypoint patterns.
    """

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)

    def find_entrypoints(self) -> List[Dict[str, str]]:
        entrypoints: List[Dict[str, str]] = []

        # 1. package.json (Node/JS/TS)
        pkg_path = os.path.join(self.repo_path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "main" in data and data["main"]:
                    entrypoints.append({
                        "type": "package.json",
                        "file": data["main"],
                        "name": "main"
                    })
                if "bin" in data and data["bin"]:
                    bins = data["bin"]
                    if isinstance(bins, dict):
                        for name, path in bins.items():
                            entrypoints.append({
                                "type": "package.json",
                                "file": path,
                                "name": name
                            })
                    elif isinstance(bins, str):
                        entrypoints.append({
                            "type": "package.json",
                            "file": bins,
                            "name": data.get("name", "bin")
                        })
            except Exception as err:
                import logging
                logging.getLogger("qbrain").warning(f"Failed to parse package.json: {err}")

        # 2. Cargo.toml (Rust)
        cargo_path = os.path.join(self.repo_path, "Cargo.toml")
        if os.path.exists(cargo_path) and tomllib is not None:
            try:
                with open(cargo_path, "rb") as f:
                    data = tomllib.load(f)
                if "bin" in data and isinstance(data["bin"], list):
                    for bin_sec in data["bin"]:
                        if "path" in bin_sec and "name" in bin_sec:
                            entrypoints.append({
                                "type": "Cargo.toml",
                                "file": bin_sec["path"],
                                "name": bin_sec["name"]
                            })
                if "lib" in data and isinstance(data["lib"], dict):
                    if "path" in data["lib"]:
                        entrypoints.append({
                            "type": "Cargo.toml",
                            "file": data["lib"]["path"],
                            "name": data["lib"].get("name", "lib")
                        })
            except Exception as err:
                import logging
                logging.getLogger("qbrain").warning(f"Failed to parse Cargo.toml: {err}")

        # 3. pyproject.toml (Python)
        pyproj_path = os.path.join(self.repo_path, "pyproject.toml")
        if os.path.exists(pyproj_path) and tomllib is not None:
            try:
                with open(pyproj_path, "rb") as f:
                    data = tomllib.load(f)
                if "project" in data and isinstance(data["project"], dict):
                    scripts = data["project"].get("scripts")
                    if isinstance(scripts, dict):
                        for name, target in scripts.items():
                            entrypoints.append({
                                "type": "pyproject.toml",
                                "file": target,
                                "name": name
                            })
                if "tool" in data and isinstance(data["tool"], dict):
                    poetry = data["tool"].get("poetry")
                    if isinstance(poetry, dict):
                        scripts = poetry.get("scripts")
                        if isinstance(scripts, dict):
                            for name, target in scripts.items():
                                entrypoints.append({
                                    "type": "pyproject.toml",
                                    "file": target,
                                    "name": name
                                })
            except Exception as err:
                import logging
                logging.getLogger("qbrain").warning(f"Failed to parse pyproject.toml: {err}")

        # 4. YAML config files
        if os.path.exists(self.repo_path) and os.path.isdir(self.repo_path):
            for filename in os.listdir(self.repo_path):
                if filename.endswith((".yaml", ".yml")):
                    yaml_file_path = os.path.join(self.repo_path, filename)
                    try:
                        with open(yaml_file_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        parsed = None
                        if yaml is not None:
                            try:
                                parsed = yaml.safe_load(content)
                            except Exception:
                                pass

                        if parsed and isinstance(parsed, dict):
                            def recurse_find(d):
                                for k, v in d.items():
                                    if k == "entrypoint" and isinstance(v, str):
                                        entrypoints.append({
                                            "type": filename,
                                            "file": v,
                                            "name": "entrypoint"
                                        })
                                    elif isinstance(v, dict):
                                        recurse_find(v)
                            recurse_find(parsed)
                        else:
                            matches = re.findall(r"entrypoint:\s*['\"]?([a-zA-Z0-9_\-\/\.]+)['\"]?", content)
                            for match in matches:
                                entrypoints.append({
                                    "type": filename,
                                    "file": match,
                                    "name": "entrypoint"
                                })
                    except Exception as err:
                        import logging
                        logging.getLogger("qbrain").warning(f"Failed to parse YAML file {filename}: {err}")

        # 5. Fallback scan
        FALLBACK_NAMES = [
            "main.cpp", "main.c", "main.go", "main.rs",
            "index.js", "index.ts", "app.py", "main.py", "index.php",
            "server.js", "server.ts", "index.jsx", "index.tsx"
        ]
        # Heuristic markers for entrypoints in non-standard files
        CONTENT_MARKERS = {
            ".php": [re.compile(r"<\?php.*?(?:require|include)(?:_once)?\s*['\"]", re.DOTALL | re.IGNORECASE)],
            ".py": [re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]")],
            ".js": [re.compile(r"app\.listen\s*\("), re.compile(r"http\.createServer\s*\(")],
        }
        
        if os.path.exists(self.repo_path) and os.path.isdir(self.repo_path):
            for root, dirs, files in os.walk(self.repo_path):
                # Prune common search dirs
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", ".venv", "venv", "__pycache__", "build", "dist")]
                for f in files:
                    is_entry = f in FALLBACK_NAMES
                    
                    if not is_entry:
                        # Check content heuristic
                        _, ext = os.path.splitext(f)
                        if ext in CONTENT_MARKERS:
                            try:
                                with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as content_f:
                                    # Read first 2KB for efficiency
                                    head = content_f.read(2048)
                                    if any(marker.search(head) for marker in CONTENT_MARKERS[ext]):
                                        is_entry = True
                            except Exception:
                                pass

                    if is_entry:
                        rel_path = os.path.relpath(os.path.join(root, f), self.repo_path)
                        rel_path = rel_path.replace("\\", "/")
                        if rel_path not in [e["file"] for e in entrypoints]:
                            entrypoints.append({
                                "type": "heuristic" if f not in FALLBACK_NAMES else "fallback",
                                "file": rel_path,
                                "name": f.split(".")[0]
                            })

        # 6. Add setup and configuration files as entrypoints
        for fpath in self.find_setup_config_files():
            rel_path = os.path.relpath(fpath, self.repo_path).replace("\\", "/")
            if rel_path not in [e["file"] for e in entrypoints]:
                entrypoints.append({
                    "type": "setup_config",
                    "file": rel_path,
                    "name": os.path.basename(fpath).split(".")[0]
                })

        # Normalize slashes
        for e in entrypoints:
            e["file"] = e["file"].replace("\\", "/")

        return entrypoints

    def find_setup_config_files(self) -> List[str]:
        """Scans for database setup and configuration files, including .dist templates."""
        setup_patterns = [
            r"config.*\.php(\.dist)?$", 
            r"bootstrap.*\.php(\.dist)?$", 
            r"common\.php(\.dist)?$", 
            r"\.env(\.dist)?$", 
            r"settings\.php(\.dist)?$", 
            r"init\.php(\.dist)?$",
            r"setup.*\.php(\.dist)?$"
        ]
        found_files = []
        if os.path.exists(self.repo_path) and os.path.isdir(self.repo_path):
            for root, dirs, files in os.walk(self.repo_path):
                # Prune common search dirs
                dirs[:] = [d for d in dirs if d not in ("obsidian_vault", ".git", "node_modules", "vendor", ".venv", "venv", "__pycache__", "build", "dist")]
                for f in files:
                    if any(re.match(pattern, f, re.IGNORECASE) for pattern in setup_patterns):
                        found_files.append(os.path.join(root, f))
        return found_files
