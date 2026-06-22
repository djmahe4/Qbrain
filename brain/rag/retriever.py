import os
import json
import re
import numpy as np
from typing import List, Dict, Any, Optional
from brain.embedder import Embedder

class VaultRetriever:
    def __init__(self, config, embedder: Embedder):
        self.config = config
        self.embedder = embedder
        self.vault_path = os.path.abspath(config.data.get("vault_path", os.path.join(config.repo_path, "obsidian_vault")))
        self.index_dir = os.path.join(self.vault_path, ".qbrain", "_rag_index")
        self.index_file = os.path.join(self.index_dir, "index.json")

    def _extract_metadata(self, filepath: str, content: str) -> Dict[str, Any]:
        """Extract archetype, type, and other frontmatter from the markdown note."""
        metadata = {}
        # Parse frontmatter if present
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if match:
            frontmatter = match.group(1)
            for line in frontmatter.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    metadata[k.strip().lower()] = v.strip().strip("'\"[]")
        
        # Fallback metadata from directory name
        rel_path = os.path.relpath(filepath, self.vault_path)
        folder = rel_path.split(os.sep)[0] if os.sep in rel_path else ""
        metadata["type"] = folder
        
        # Parse archetype if not in frontmatter
        if "archetype" not in metadata:
            arch_match = re.search(r"Archetype:\s*`?([\w\-]+)`?", content, re.IGNORECASE)
            if arch_match:
                metadata["archetype"] = arch_match.group(1).lower()
        return metadata

    def _extract_enriched_fields(self, rel_path: str, content: str) -> Dict[str, Any]:
        """Extract dataflow_summary, security_level, entanglement_count, and note_type from content."""
        # 1. dataflow_summary: first TAINTED row from Dynamic Variable Tracking table
        dataflow_summary = ""
        for line in content.splitlines():
            if "TAINTED" in line and line.strip().startswith("|") and not "Variable" in line and not "---" in line:
                dataflow_summary = line.strip()
                break

        # 2. security_level: value from Assumed Environmental Context or content
        security_level = None
        env_match = re.search(r"##+\s*Assumed Environmental Context\s*\n(.*?)(?=\n##+|\Z)", content, re.DOTALL | re.IGNORECASE)
        search_text = env_match.group(1) if env_match else content
        sec_level_match = re.search(r"==\s*['\"]([^'\"]+)['\"]", search_text)
        if sec_level_match:
            security_level = sec_level_match.group(1)

        # 3. entanglement_count: count of Inbound Callers listed in Entanglements
        entanglement_count = 0
        callers_match = re.search(r"### Inbound Callers\s*\n(.*?)(?:###|\Z)", content, re.DOTALL | re.IGNORECASE)
        if callers_match:
            entanglement_count = len(re.findall(r"-\s*\[\[", callers_match.group(1)))

        # 4. note_type
        folder = rel_path.split("/")[0] if "/" in rel_path else "unknown"
        note_type_map = {
            "symbols": "symbol",
            "behaviors": "behavior",
            "files": "file",
            "narratives": "narrative",
            "rules": "rule"
        }
        note_type = note_type_map.get(folder, folder)

        return {
            "dataflow_summary": dataflow_summary,
            "security_level": security_level,
            "entanglement_count": entanglement_count,
            "note_type": note_type
        }

    def build_index(self, force: bool = False) -> List[Dict[str, Any]]:
        """Indexes all markdown files in the obsidian vault."""
        os.makedirs(self.index_dir, exist_ok=True)
        
        existing_index = {}
        if os.path.exists(self.index_file) and not force:
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        if "dataflow_summary" not in item:
                            enriched = self._extract_enriched_fields(item["file_path"], item.get("content", ""))
                            item.update(enriched)
                        existing_index[item["file_path"]] = item
            except Exception:
                pass
                
        updated_items = []
        has_changes = False
        stale_files = []
        
        # Scan vault folders
        subdirs = ["files", "symbols", "behaviors", "narratives", "rules"]
        for subdir in subdirs:
            subdir_path = os.path.join(self.vault_path, subdir)
            if not os.path.exists(subdir_path):
                continue
            for root, _, files in os.walk(subdir_path):
                for f in files:
                    if f.endswith(".md"):
                        filepath = os.path.join(root, f)
                        rel_path = os.path.relpath(filepath, self.vault_path).replace("\\", "/")
                        mtime = os.path.getmtime(filepath)
                        
                        # Check if we can reuse the existing entry
                        if rel_path in existing_index and existing_index[rel_path].get("mtime") == mtime:
                            updated_items.append(existing_index[rel_path])
                        else:
                            stale_files.append((filepath, rel_path, mtime))
                            
        if len(stale_files) > 50 and not force and existing_index:
            # Too many stale files. To avoid a huge synchronous hit (e.g. during tests),
            # we just return the existing index and defer the background build.
            import threading
            def _bg_rebuild():
                self.build_index(force=True)
            threading.Thread(target=_bg_rebuild, daemon=True).start()
            return list(existing_index.values())

        for filepath, rel_path, mtime in stale_files:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as file_handle:
                    content = file_handle.read()
                metadata = self._extract_metadata(filepath, content)
                embedding = self.embedder.embed(content).tolist()
                enriched = self._extract_enriched_fields(rel_path, content)
                
                item = {
                    "file_path": rel_path,
                    "content": content,
                    "metadata": metadata,
                    "mtime": mtime,
                    "embedding": embedding
                }
                item.update(enriched)
                updated_items.append(item)
                has_changes = True
            except Exception:
                pass
                                
        if has_changes or len(updated_items) != len(existing_index):
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(updated_items, f, indent=2)
        return updated_items

    def retrieve(self, query: str, top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Retrieves top-K relevant vault notes based on query similarity and filters."""
        items = self.build_index()
        if not items:
            return []
            
        # Embed query
        query_vector = self.embedder.embed(query)
        
        # Tokenize query for lexical overlap
        query_tokens = set(re.findall(r"\w+", query.lower()))
        
        results = []
        for item in items:
            # Grounding/filtering
            if filters:
                match = True
                item_metadata = item.get("metadata", {})
                for k, v in filters.items():
                    val = item_metadata.get(k.lower())
                    if val != v:
                        match = False
                        break
                if not match:
                    continue
                    
            # Similarity
            item_vector = np.array(item["embedding"])
            similarity = self.embedder.cosine_similarity(query_vector, item_vector)
            
            # Simple lexical boost
            boost = 0.0
            filename_lower = os.path.basename(item["file_path"]).lower()
            content_lower = item["content"].lower()
            for token in query_tokens:
                if len(token) < 3:
                    continue
                if token in filename_lower:
                    boost += 0.08
                elif token in content_lower:
                    boost += 0.02
            
            final_score = similarity + boost
            
            results.append({
                "file_path": item["file_path"],
                "content": item["content"],
                "metadata": item["metadata"],
                "similarity": final_score,
                "dataflow_summary": item.get("dataflow_summary", ""),
                "security_level": item.get("security_level", None),
                "entanglement_count": item.get("entanglement_count", 0),
                "note_type": item.get("note_type", "unknown")
            })
            
        # Sort by similarity descending
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
