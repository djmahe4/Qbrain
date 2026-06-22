import numpy as np
from typing import List, Union
from sentence_transformers import SentenceTransformer

class Embedder:
    _model = None

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name

    def _get_model(self):
        if Embedder._model is None:
            # Lazy load sentence-transformers to speed up startup times when not embedding
            try:
                import os
                import platform
                if platform.system() == "Windows":
                    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\mahes")
                    cache_dir = os.path.join(user_profile, ".qbrain_models")
                else:
                    cache_dir = os.path.expanduser("~/.qbrain_models")
                os.makedirs(cache_dir, exist_ok=True)
                Embedder._model = SentenceTransformer(self.model_name, cache_folder=cache_dir)
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is not installed. Please install it to use semantic embedding features."
                ) from e
        return Embedder._model

    def embed(self, texts: Union[str, List[str]]) -> np.ndarray:
        """
        Embed a single text or a list of texts.
        Returns a numpy array of embeddings.
        """
        model = self._get_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        return embeddings

    @staticmethod
    def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
        """
        Compute the cosine similarity between two vectors.
        """
        dot_product = np.dot(v1, v2)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return float(dot_product / (norm_v1 * norm_v2))

    @staticmethod
    def semantic_distance(v1: np.ndarray, v2: np.ndarray) -> float:
        """
        Compute semantic distance: 1 - cosine_similarity.
        """
        return 1.0 - Embedder.cosine_similarity(v1, v2)
