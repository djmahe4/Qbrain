"""
brain/business_logic_mapper.py
Extracts and categorizes business logic rules from multi-language DocstringGenomes.
Writes BUSINESS_RULE nodes and IMPLEMENTS edges to the MCP graph.

Rule categories:
    validation    — input checks, schema enforcement, constraint validation
    authorization — ownership, access control, permissions
    computation   — mathematical operations, calculations, transformations
    io            — file/network/database I/O operations
    event         — event emission, logging, notifications
"""
import re
from typing import Any, Dict, List, Optional
from brain.indexer import Indexer
from brain.logger import get_logger

logger = get_logger(__name__)



# ─────────────────────────── Constants ───────────────────────────

RULE_CATEGORIES: List[str] = [
    "validation",
    "authorization",
    "computation",
    "io",
    "event",
]

# Keyword sets for each category (lowercase)
_CATEGORY_KEYWORDS: Dict[str, set] = {
    "authorization": {
        "owner", "only", "access", "permission", "role", "admin",
        "authorize", "authorized", "restrict", "restricted", "privilege",
        "onlyowner", "requires", "caller", "sender", "whitelist", "blacklist",
    },
    "validation": {
        "valid", "validate", "validates", "check", "checks", "verify", "verifies",
        "ensures", "assert", "require", "constraint", "schema", "format",
        "length", "range", "zero", "null", "empty", "invalid", "sanitize",
    },
    "computation": {
        "calculate", "calculates", "compute", "computes", "hash", "sign", "encrypt",
        "multiply", "divide", "sum", "average", "aggregate", "formula",
        "interest", "price", "score", "weight", "balance",
    },
    "io": {
        "fetch", "read", "write", "save", "load", "store", "database", "db",
        "http", "api", "request", "response", "upload", "download", "file",
        "stream", "socket", "network", "send", "receive",
    },
    "event": {
        "emit", "emits", "event", "log", "logs", "notify", "notification",
        "trigger", "dispatch", "publish", "broadcast", "webhook", "callback",
    },
}


def _score_category(text: str, category: str) -> float:
    """
    Score how strongly a text snippet matches a business rule category.
    Returns a float in [0.0, 1.0].
    """
    words = set(re.split(r"\W+", text.lower()))
    keywords = _CATEGORY_KEYWORDS[category]
    matched = words & keywords
    if not matched:
        return 0.0
    # Score: fraction of category keywords hit, capped at 1.0
    return min(len(matched) / max(len(keywords) * 0.1, 1.0), 1.0)


def _best_category(text: str) -> Optional[str]:
    """Return the highest-scoring category for a text, or None if all scores < threshold."""
    scores = {cat: _score_category(text, cat) for cat in RULE_CATEGORIES}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0.0 else None


# ─────────────────────────── BusinessRule ───────────────────────────

class BusinessRule:
    """A typed business rule extracted from a function's docstring genome."""

    def __init__(self, category: str, description: str, source_function: str, confidence: float):
        if category not in RULE_CATEGORIES:
            raise ValueError(f"Invalid category '{category}'. Must be one of: {RULE_CATEGORIES}")
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"Confidence must be in [0.0, 1.0], got {confidence}")
        self.category = category
        self.description = description
        self.source_function = source_function
        self.confidence = confidence

    def __repr__(self) -> str:
        return (f"BusinessRule(category={self.category!r}, "
                f"fn={self.source_function!r}, confidence={self.confidence:.2f})")


# ─────────────────────────── BusinessLogicMapper ───────────────────────────

class BusinessLogicMapper:
    """
    Maps DocstringGenome dicts to BusinessRule objects and persists them to the MCP graph.
    """

    # Threshold above which a rule is considered confident enough to write
    CONFIDENCE_THRESHOLD = 0.0

    def __init__(self, indexer: Indexer):
        self.indexer = indexer

    def extract_rules(self, genome: Dict[str, Any]) -> List[BusinessRule]:
        """
        Extract BusinessRule objects from a single DocstringGenome dict.

        Sources:
        1. `business_rules` list (pre-extracted by LanguageParser)
        2. `docstring` body (keyword scanning fallback)
        """
        func_name = genome.get("name", "unknown")
        rules: List[BusinessRule] = []

        # 1. From pre-extracted business_rules list
        for rule_text in (genome.get("business_rules") or []):
            cat = _best_category(rule_text)
            if cat:
                confidence = _score_category(rule_text, cat)
                rules.append(BusinessRule(cat, rule_text, func_name, confidence))

        # 2. Fallback: scan docstring body if no rules extracted
        docstring = genome.get("docstring") or ""
        if not rules and docstring.strip():
            cat = _best_category(docstring)
            if cat:
                confidence = _score_category(docstring, cat)
                # Cap confidence at 0.6 for fallback docstring scan
                rules.append(BusinessRule(cat, docstring[:200].strip(), func_name, min(confidence, 0.6)))


        # 3. New: Scan code_snippet for technical markers
        code = genome.get("code_snippet") or ""
        if code:
            # Authorization markers: decorators or common check functions
            if re.search(r"@\w*(authorized|requires|guard|protected|auth)\b", code, re.IGNORECASE) or \
               re.search(r"\b(check_permission|is_admin|has_role|authorize)\s*\(", code, re.IGNORECASE):
                rules.append(BusinessRule("authorization", "Technical authorization check detected in code", func_name, 0.85))
            
            # Validation markers: schema library usage
            if re.search(r"\b(zod|yup|joi|validator|schema)\.(parse|validate|check)\b", code, re.IGNORECASE):
                rules.append(BusinessRule("validation", "Technical schema validation detected in code", func_name, 0.85))

        return rules

    def write_rules_to_graph(self, rules: List[BusinessRule]) -> None:
        """
        Write BUSINESS_RULE nodes and IMPLEMENTS edges to the MCP graph and local sidecar.
        Optimistic write to MCP graph: fails silently with a warning if the graph is read-only.
        """
        if not rules:
            return
            
        # 1. Internal Write (Cognitive Persistence)
        for rule in rules:
            belief_state = {
                "beliefs": {rule.category: rule.confidence},
                "status": "ACTIVE" if rule.confidence > 0.8 else "SUPERPOSITION",
                "winner": rule.category if rule.confidence > 0.8 else None,
                "support_mass": rule.confidence
            }
            self.indexer.persistence.persist_belief(rule.source_function, belief_state, external=True)

        logger.info(f"Persisted {len(rules)} business logic rules via PersistenceManager.")

        # 2. External Graph Write
        merge_nodes: List[str] = []
        merge_edges: List[str] = []

    def write_rules_to_graph(self, rules: List[BusinessRule]) -> None:
        """
        Persist business logic rules to the internal mind (SQLite).
        Graph writes (MERGE) are skipped as they are not supported by codebase-memory-mcp.
        """
        if not rules:
            return
            
        # 1. Internal Write (Cognitive Persistence)
        for rule in rules:
            belief_state = {
                "beliefs": {rule.category: rule.confidence},
                "status": "ACTIVE" if rule.confidence > 0.8 else "SUPERPOSITION",
                "winner": rule.category if rule.confidence > 0.8 else None,
                "support_mass": rule.confidence
            }
            self.indexer.persistence.persist_belief(rule.source_function, belief_state, external=False)

        logger.info(f"Persisted {len(rules)} business logic rules to the Internal Mind (SQLite).")

        # Graph updates (MERGE/SET) are currently unsupported and cause failures.
        # We rely on the Librarian to merge SQLite and Graph data during sync.
    def map_all(self, genomes: List[Dict[str, Any]]) -> List[BusinessRule]:
        """
        Process all genomes: extract rules and write them to the graph.

        Returns the full list of extracted BusinessRule objects.
        """
        if not genomes:
            return []

        all_rules: List[BusinessRule] = []
        for genome in genomes:
            rules = self.extract_rules(genome)
            all_rules.extend(rules)

        if all_rules:
            self.write_rules_to_graph(all_rules)

        return all_rules
