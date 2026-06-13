import pytest
import numpy as np
from brain.lru_tracker import LRUSemanticCache

def test_lru_cache_operations():
    cache = LRUSemanticCache(maxsize=3)

    v1 = np.array([1.0, 0.0])
    v2 = np.array([0.0, 1.0])
    v3 = np.array([0.707, 0.707])
    v4 = np.array([1.0, 1.0])

    cache.put("a", v1)
    cache.put("b", v2)
    cache.put("c", v3)

    # All inside
    assert cache.get("a") is not None
    assert cache.get("b") is not None
    assert cache.get("c") is not None

    # Update cache access order by querying "a"
    cache.get("a")

    # Add v4, should evict "b" (since "a" was queried, "c" is newer)
    cache.put("d", v4)

    assert cache.get("b") is None
    assert "b" in cache.get_evicted()
    assert cache.get("a") is not None
    assert cache.get("c") is not None
    assert cache.get("d") is not None
