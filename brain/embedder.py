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
                cache_dir = os.path.join(os.path.expanduser("~"), ".qbrain_models")
                os.makedirs(cache_dir, exist_ok=True)
                Embedder._model = SentenceTransformer(self.model_name, cache_folder=cache_dir)
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is not installed. Please install it to use semantic embedding features."
                ) from e
        return Embedder._model

    @staticmethod
    def select_amplitude_lines(content: str, limit: int = 40) -> List[str]:
        """
        Quantum-inspired amplitude filter.
        Uses a Hamiltonian energy model and the Born rule to select the top N
        most information-dense lines from a text to fit within embedding limits.
        Preserves original line order.
        """
        import re
        import math
        
        lines = content.split('\n')
        if len(lines) <= limit:
            return lines

        # 1. Calculate Hamiltonian Energy (H_i) for each line
        energies = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                energies.append(0.0) # Vacuum state
                continue

            energy = 1.0 # Ground state energy

            # Structural boosts (Headings, functions, imports, exports, decorators)
            if re.match(r'^(import|export|const|function|class|def|struct|impl|fn|use|require)\b', trimmed) or trimmed.startswith("@"):
                energy += 3.0 # High-signal code constructs
            if re.match(r'^#+\s+', trimmed):
                energy += 4.0 # Markdown headings / section bounds
            if any(kw in trimmed for kw in ['instanceof', 'typeof', 'return', 'yield', 'throw', 'raise']):
                energy += 1.5

            # Length penalty/reward (normalizing long lines to prevent noise from dominating)
            length_factor = min(len(trimmed) / 100.0, 2.0)
            energy += length_factor

            energies.append(energy)

        # Temperature parameter T to scale the distribution
        T = 2.0

        # 2. Compute partition function (normalization denominator)
        exp_energies = [math.exp(E / T) for E in energies]
        partition_function = sum(exp_energies)

        if partition_function == 0:
            return lines[:limit]

        # 3. Apply Born Rule to get probability amplitudes
        line_probabilities = []
        for idx, line in enumerate(lines):
            line_probabilities.append({
                "index": idx,
                "line": line,
                "probability": exp_energies[idx] / partition_function
            })

        # 4. Sort by probability, slice top N, and sort back by original index to preserve flow
        line_probabilities.sort(key=lambda x: x["probability"], reverse=True)
        top_slice = line_probabilities[:limit]
        top_slice.sort(key=lambda x: x["index"])

        return [item["line"] for item in top_slice]

    def embed(self, texts: Union[str, List[str]]) -> np.ndarray:
        """
        Embed a single text or a list of texts, automatically applying the 
        quantum amplitude filter to long texts to stay within the 256-token limit.
        Returns a numpy array of embeddings.
        """
        model = self._get_model()
        
        # Apply amplitude pruning to any text exceeding 40 lines
        if isinstance(texts, str):
            processed_texts = "\n".join(self.select_amplitude_lines(texts, limit=40))
        else:
            processed_texts = ["\n".join(self.select_amplitude_lines(t, limit=40)) for t in texts]
            
        embeddings = model.encode(processed_texts, convert_to_numpy=True)
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
