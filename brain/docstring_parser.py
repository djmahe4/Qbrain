from typing import List, Dict, Any
from brain.indexer import Indexer
from brain.language_parser import LanguageParser, build_genome as _build_genome_multilang


class DocstringParser:
    def __init__(self, indexer: Indexer):
        self.indexer = indexer
        self._lang_parser = LanguageParser()

    def get_functions_with_docstrings(self) -> List[Dict[str, Any]]:
        """
        Query functions and retrieve metadata.
        Filters out non-code files like READMEs, JSON, etc.
        """
        query = (
            "MATCH (f) "
            "WHERE f:Function OR f:Method OR f:Module "
            "RETURN f.name AS name, f.docstring AS docstring, "
            "       COALESCE(f.file_path, f.file) AS file, "
            "       COALESCE(f.start_line, f.line) AS line, "
            "       f.end_line AS end_line, "
            "       f.signature AS signature, f.language AS language, labels(f) AS labels"
        )
        results = self.indexer.query_graph(query)
        
        # Post-process to exclude documentation and config files
        filtered = []
        excluded_exts = {".md", ".json", ".txt", ".yaml", ".yml", ".lock", ".log"}
        excluded_names = {"readme", "changelog", "license", "contributors", "authors"}
        
        for f in results:
            path = (f.get("file") or "").lower()
            name = (f.get("name") or "").lower()
            
            is_doc = any(path.endswith(ext) for ext in excluded_exts)
            is_meta = any(ex_name in path or ex_name in name for ex_name in excluded_names)
            
            if not (is_doc or is_meta):
                filtered.append(f)
                
        return filtered

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
