import re
import numpy as np
from typing import List, Set, Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class EntangledPair:
    comment_text: str
    comment_file: str
    comment_line: int
    symbol_name: str
    cosine_score: float
    flip_detected: bool = False     # comment intent contradicts belief/taint
    flip_reason: str = ""
    decoherence: bool = False       # symbol referenced in comment no longer in graph

class QuantumCorrelator:
    """
    Semantic correlation between extracted comments and live symbol context.
    
    Entanglement  → cosine(comment_emb, symbol_emb) > threshold
    Flip          → comment business_rule contradicts symbol's belief.winner or taint
    Decoherence   → comment references a name absent from current graph node set
    """

    def entangle(self, comments: List[Dict[str, Any]], beliefs: Dict[str, Any], embedder, threshold: float = 0.72) -> List[EntangledPair]:
        """
        Calculates pairwise cosine similarity matrix between comments and symbols.
        Returns a list of EntangledPair objects matching threshold.
        """
        if not comments or not beliefs:
            return []

        # Get list of fully qualified symbol names
        symbols = [s for s in beliefs.keys() if ":" in s]
        if not symbols:
            # Fallback to all keys if none contain colons
            symbols = list(beliefs.keys())

        # Generate texts to embed
        comment_texts = [c.get("docstring") or c.get("comment_text") or "" for c in comments]
        symbol_texts = [s.split(":")[-1] for s in symbols]  # embed display name for correlation

        try:
            comment_embs = embedder.embed(comment_texts)
            symbol_embs = embedder.embed(symbol_texts)
        except Exception:
            return []

        # Convert to numpy arrays if they are lists
        if isinstance(comment_embs, list):
            comment_embs = np.array(comment_embs)
        if isinstance(symbol_embs, list):
            symbol_embs = np.array(symbol_embs)

        # Enforce 2D arrays
        if len(comment_embs.shape) == 1:
            comment_embs = comment_embs.reshape(1, -1)
        if len(symbol_embs.shape) == 1:
            symbol_embs = symbol_embs.reshape(1, -1)

        # Vectorized cosine similarity computation using NumPy
        c_norms = np.linalg.norm(comment_embs, axis=1, keepdims=True)
        s_norms = np.linalg.norm(symbol_embs, axis=1, keepdims=True)
        c_norms[c_norms == 0] = 1.0
        s_norms[s_norms == 0] = 1.0

        c_embs_norm = comment_embs / c_norms
        s_embs_norm = symbol_embs / s_norms

        similarity_matrix = np.dot(c_embs_norm, s_embs_norm.T)
        
        pairs = []
        for i, comment in enumerate(comments):
            # Find the best matching symbol for this comment
            best_idx = int(np.argmax(similarity_matrix[i]))
            best_score = float(similarity_matrix[i, best_idx])

            if best_score >= threshold:
                matched_symbol = symbols[best_idx]
                
                # Safe line number parsing
                raw_line = comment.get("line")
                try:
                    line_num = int(raw_line) if raw_line is not None else 0
                except (ValueError, TypeError):
                    line_num = 0

                pairs.append(EntangledPair(
                    comment_text=comment.get("docstring") or comment.get("comment_text") or "",
                    comment_file=comment.get("file", "unknown"),
                    comment_line=line_num,
                    symbol_name=matched_symbol,
                    cosine_score=best_score
                ))

        return pairs

    def detect_flips(self, pairs: List[EntangledPair], beliefs: Dict[str, Any]) -> List[EntangledPair]:
        """
        Checks comments for intent contradictions against the dynamic beliefs of the symbol.
        """
        for pair in pairs:
            symbol_info = beliefs.get(pair.symbol_name, {})
            winner = symbol_info.get("winner", "SAFE")
            
            text_lower = pair.comment_text.lower()
            
            # Heuristic 1: Sanitizes/checks but is classified as TAINTED/SINK
            if any(w in text_lower for w in ["validate", "sanitize", "check", "clean"]):
                if winner in ("TAINTED", "SINK"):
                    pair.flip_detected = True
                    pair.flip_reason = f"Comment claims validation but winner status is {winner} (contradicts safety)"
                    continue

            # Heuristic 2: claims public/unauthenticated in an admin/auth-required zone
            is_auth_required = any(k in pair.symbol_name.lower() or k in pair.comment_file.lower() for k in ["admin", "auth", "secure", "private"])
            has_public_claim = any(k in text_lower for k in ["public", "unauthenticated", "anonymous", "guest"])
            if is_auth_required and has_public_claim:
                pair.flip_detected = True
                pair.flip_reason = "Comment claims public/unauthenticated but symbol is in auth-required zone"
                continue

            # Heuristic 3: Claims deterministic return but winner is superposition
            if any(w in text_lower for w in ["always returns", "guaranteed", "never"]):
                if winner == "SUPERPOSITION":
                    pair.flip_detected = True
                    pair.flip_reason = "Comment claims deterministic response but winner is in non-deterministic SUPERPOSITION"
                    continue

        return pairs

    def detect_decoherence(self, pairs: List[EntangledPair], graph_symbol_names: Set[str]) -> List[EntangledPair]:
        """
        Checks if the comment refers to variables or functions that are not present in current graph symbols.
        """
        short_names = {name.split(":")[-1] for name in graph_symbol_names}
        
        for pair in pairs:
            # Match backticked names like `my_func`
            words = re.findall(r'`([^`]+)`', pair.comment_text)
            # Match snake_case or camelCase-like words that look like identifiers
            words += [w for w in re.findall(r'\b[a-zA-Z_]\w+\b', pair.comment_text) if len(w) > 3]
            
            ghosts = []
            for word in words:
                if word in ["Function", "Method", "Class", "Interface", "Enum", "Module", "Variable"]:
                    continue
                is_symbol_like = "_" in word or (word[0].islower() and any(c.isupper() for c in word)) or word[0].isupper()
                if is_symbol_like and word not in short_names:
                    ghosts.append(word)
            
            if ghosts:
                pair.decoherence = True
                pair.flip_reason = f"References ghost symbols: {', '.join(set(ghosts))}"
                
        return pairs

    def to_context_summary(self, pairs: List[EntangledPair]) -> str:
        """Produce a compact text block for SLM consumption."""
        lines = []
        for pair in pairs:
            status = []
            if pair.flip_detected:
                status.append(f"FLIP ({pair.flip_reason})")
            if pair.decoherence:
                status.append("DECOHERENCE")
            
            status_str = f" [{', '.join(status)}]" if status else ""
            lines.append(
                f"- Comment in {pair.comment_file}:{pair.comment_line} entangled with {pair.symbol_name} "
                f"(cosine: {pair.cosine_score:.2f}){status_str}"
            )
        return "\n".join(lines)

    def persist(self, pairs: List[EntangledPair], persistence) -> None:
        """Write to entanglements table."""
        for pair in pairs:
            ent_type = "COMMENT_ENTANGLE"
            if pair.flip_detected:
                ent_type = "COMMENT_FLIP"
            elif pair.decoherence:
                ent_type = "DECOHERENCE"
                
            source_key = f"{pair.comment_file}:{pair.comment_line}"
            persistence.persist_entanglement(
                source=source_key,
                target=pair.symbol_name,
                ent_type=ent_type,
                source_file=pair.comment_file
            )
