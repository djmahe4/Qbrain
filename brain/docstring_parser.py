from typing import List, Dict, Any
from brain.indexer import Indexer
from brain.language_parser import LanguageParser, build_genome as _build_genome_multilang


class DocstringParser:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self._lang_parser = LanguageParser()

    def get_functions_with_docstrings(self) -> List[Dict[str, Any]]:
        """
        Query functions and retrieve names, docstrings, filenames, lines, and language.
        The 'language' field is included so that multi-language genome building works correctly.
        """
        query = (
            "MATCH (f:Function) "
            "RETURN f.name AS name, f.docstring AS docstring, f.file AS file, f.line AS line, "
            "f.complexity AS complexity, f.sideEffects AS sideEffects, f.isExported AS isExported, "
            "f.signature AS signature, f.language AS language"
        )
        try:
            results = self.indexer.query_graph(query)
            # Handle standard nested JSON response format from query_graph
            # Standard output might look like: {"results": [...]} or a raw list of dicts.
            if isinstance(results, dict):
                return results.get("results", [])
            elif isinstance(results, list):
                return results
            return []
        except Exception:
            # Return empty if graph query fails (e.g. no database yet initialized)
            return []

    def parse_genome(self, func: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a raw function record into a full multi-language DocstringGenome dict.
        Includes params, returns, business_rules, and detected language.
        """
        return self._lang_parser.parse(func)

    @staticmethod
    def build_genome(func: Dict[str, Any]) -> str:
        """
        Build a semantic genome string from a function record.
        Uses multi-language parsing for richer genome construction.
        Backward-compatible: accepts raw MCP function dicts.
        """
        return _build_genome_multilang(func) if (
            func.get("business_rules") or func.get("params")
        ) else _legacy_build_genome(func)


def _legacy_build_genome(func: Dict[str, Any]) -> str:
    """
    Legacy genome builder: name + signature + docstring.
    Used when no structured genome fields are present (pre-parse records).
    """
    name = func.get("name", "unknown")
    sig = func.get("signature") or ""
    doc = func.get("docstring") or ""

    sig_part = f"({sig})" if sig else ""
    doc_part = f" — {doc}" if doc else ""

    return f"{name}{sig_part}{doc_part}"
