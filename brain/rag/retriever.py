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

    def build_index(self, force: bool = False) -> List[Dict[str, Any]]:
        """Indexes all markdown files in the obsidian vault."""
        os.makedirs(self.index_dir, exist_ok=True)
        
        existing_index = {}
        if os.path.exists(self.index_file) and not force:
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        existing_index[item["file_path"]] = item
            except Exception:
                pass
                
        updated_items = []
        has_changes = False
        
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
                            try:
                                with open(filepath, "r", encoding="utf-8", errors="ignore") as file_handle:
                                    content = file_handle.read()
                                metadata = self._extract_metadata(filepath, content)
                                embedding = self.embedder.embed(content).tolist()
                                updated_items.append({
                                    "file_path": rel_path,
                                    "content": content,
                                    "metadata": metadata,
                                    "mtime": mtime,
                                    "embedding": embedding
                                })
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
            results.append({
                "file_path": item["file_path"],
                "content": item["content"],
                "metadata": item["metadata"],
                "similarity": similarity
            })
            
        # Sort by similarity descending
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]
