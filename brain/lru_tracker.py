from collections import OrderedDict
import numpy as np
from typing import Optional, List, Tuple
from brain.embedder import Embedder

class LRUSemanticCache:
    def __init__(self, maxsize: int = 512):
        self.maxsize = maxsize
        self.cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self.evicted_keys: List[str] = []

    def get(self, key: str) -> Optional[np.ndarray]:
        if key not in self.cache:
            return None
        # Move to end to represent recently used
        val = self.cache[key]
        self.cache.move_to_end(key)
        return val

    def put(self, key: str, embedding: np.ndarray) -> None:
        if key in self.cache:
            self.cache[key] = embedding
            self.cache.move_to_end(key)
            return

        self.cache[key] = embedding
        if len(self.cache) > self.maxsize:
            # Pop the first element (least recently used)
            oldest_key, _ = self.cache.popitem(last=False)
            self.evicted_keys.append(oldest_key)
            # Cap evicted keys history
            if len(self.evicted_keys) > 100:
                self.evicted_keys.pop(0)

    def drift(self, key: str, new_embedding: np.ndarray) -> float:
        """
        Calculates semantic drift (distance) between cached and new embedding.
        If not in cache, returns 0.0.
        """
        old_emb = self.get(key)
        if old_emb is None:
            return 0.0
        return Embedder.semantic_distance(old_emb, new_embedding)

    def get_evicted(self) -> List[str]:
        """
        Return the list of recently evicted keys.
        """
        return list(self.evicted_keys)

    def clear_evicted(self) -> None:
        self.evicted_keys.clear()
