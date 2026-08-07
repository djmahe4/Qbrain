# MCP Contract — codebase-memory-mcp

Frozen contract for the Quant-BLM Context Builder Agent and all higher agents that consume static graph facts.

This document records the exact rules derived from the MCP documentation and the concrete worked examples. Field names that are still unverified against a live schema snapshot are marked **VERIFY**.

---

## 1. Identity key (composite)

```
UNIQUE(project, qualified_name)
```

- Every node is identified by the pair `(project, qualified_name)`.
- Short names are never used as identity. Always call `search_graph` (or an equivalent exact lookup) first, then operate on the returned `qualified_name`.
- When following a `CROSS_*` edge, switch the working project to the edge’s target project before resolving the next hop.
- Edge identity for cross-service work:  
  `(source_project, source_qn) → (edge_type, target_project, target_qn)`.

Never collapse two projects into one namespace.

---

## 2. Pagination rules per tool

| Tool            | Mechanism                          | Cap / limit                         | Notes |
|-----------------|------------------------------------|-------------------------------------|-------|
| `query_graph`   | Cursor-based (`has_more` / `nextCursor`) + `LIMIT` inside Cypher | Aggregate queries capped at **200 rows** | Page size ≤ 100 recommended. Loop while `has_more`. |
| `search_graph`  | `limit` / `offset`                 | Server-defined                     | Classic offset paging. |
| `search_code`   | `limit` only (no offset)           | Truncation signalled by `total_grep_matches` / `total_results` | Raise limit or narrow filters if truncated. |
| `trace_path`    | Depth-limited BFS (depth 1–5)      | No cursor; depth-truncated           | Re-seed frontier iteratively; do not expect a single deep dump. |

**VERIFY** before hard-coding parsers: exact JSON keys (`has_more` vs `hasMore`, `nextCursor` vs `next_cursor`) and the precise way a cursor is supplied on the next call (`AFTER {cursor}` in the Cypher string vs a separate tool argument). Capture a live snapshot with `get_graph_schema` + one real `query_graph` response.

Recommended default for route enumeration:

```text
LIMIT 100  + cursor loop until !has_more
```

---

## 3. CoverageGate policy (partial-parse / incomplete graph)

Two independent incompleteness paths exist:

1. **Graph-node incompleteness** (`coverage_note` / `parse_partial`)  
   Some constructs in the noted line ranges were not indexed.  
   The source text returned by `get_code_snippet` is still read from disk and is treated as **ground truth** for the lines shown.  
   Graph neighbours / DATA_FLOWS / CALLS leaving that range may be absent.

2. **Snippet truncation**  
   Snippet is `start_line..end_line`. If `end_line` is missing the server falls back to a default window, which can cut the function short.

**Agent behaviour (never silently skip):**

1. If `coverage_note` is present → flag the fact / finding as `coverage_uncertain`, still use the returned source for the lines shown.
2. If the snippet looks truncated (no matching closing brace, ends abruptly) → controlled raw-file read **only** under the indexed `root_path` of that project (allow-list). Never open arbitrary paths.
3. Absence of graph neighbours is **ambiguous** under partial coverage. Never interpret missing callers/callees as “no callers”. Call coverage checks for every path cited in a negative or exhaustive claim.

---

## 4. DATA_FLOWS & taint semantics

- Typed taint is **not available** for most languages (`properties=null`).
- DATA_FLOWS edges are structural (arg→param, field-access chains) and are evidence of **presence only**.
- Absence of a DATA_FLOWS edge never proves non-taint.
- Known flow-breaking patterns (object rebuild / spread helpers, certain Haskell / OCaml / Scala / Ruby constructs) must be tagged `rebuild_may_lose` (or equivalent) and fall back to source inspection.

Emit provenance on every hop:

```json
{
  "value": "...",
  "qn": "services.payments.authorize",
  "file": "src/services/payments.ts",
  "line": 21,
  "how": "arg->param" | "field_access" | "rebuild_may_lose"
}
```

---

## 5. detect_changes risk model

- Risk classification is **purely structural** (blast radius).
- No semantic / sink-aware heuristics are applied by the server.
- Use `detect_changes` only as a prioritisation pre-filter.
- Final severity is owned by the RiskClassifier / Language Subagent after `get_code_snippet` + rule evaluation.

---

## 6. Fact emission shape (Context Builder → downstream agents)

Every intermediate result is emitted as a normalised JSON fact:

```json
{
  "source": "endpoint_enumerator" | "source_sink_result" | "coverage_flag" | ...,
  "project": "payments-service",
  "payload": { ... tool-specific normalised data ... },
  "timestamp": 1710000000.0,
  "hash": optional DATG state hash
}
```

Canonical stages and their payload keys:

| Stage                 | `source` value          | Key fields in `payload` |
|-----------------------|-------------------------|-------------------------|
| Index                 | `index_result`          | `project`, `nodes`, `edges`, `coverage` |
| Enumerate entry points| `endpoint_enumerator`   | `project`, `routes[]` (`http_method`, `path`, `qualified_name`) |
| Resolve symbol        | `symbol_resolved`       | `qualified_name`, `file`, `start_line`, `end_line` |
| Reachability          | `reachability`          | `root`, `nodes[]`, `edges[]` (CALLS / DATA_FLOWS) |
| Sink inspection       | `source_sink_result`    | `entry`, `flow_edges[]`, `findings[]` (`sink`, `target_qn`, `via`, `coverage_note`, `severity`) |
| Change gate           | `change_impact`         | `changed_symbols[]`, `summary` |

Downstream agents (Language Subagent, Logic Specifier, Invariant Verifier) consume only these structured facts; they never parse raw CLI text.

---

## 7. Required call sequence (Context Builder playbook)

1. `index_repository` (if needed)
2. `query_graph` — `MATCH (r:Route)-[:HANDLES]->(h:Function) …` (paginated)
3. For each handler: `search_graph` → confirm exact `qualified_name`
4. `trace_path` (direction=`both`, depth-limited, frontier re-seeding)
5. For each reached candidate sink: `get_code_snippet(include_neighbors=true)` → apply CoverageGate + semantic rules
6. (Optional CI) `detect_changes` → prioritise high blast-radius symbols

Never pass a short/ambiguous name past step 3.

---

## 8. Open verification items

Before locking parsers in production code:

- [ ] Live snapshot of `query_graph` / `trace_path` / `get_code_snippet` JSON (exact field names)
- [ ] Confirm cursor injection syntax (`AFTER {cursor}` vs separate argument)
- [ ] Exact shape of `CROSS_*` edge payload (`source_project`, `target_project`, …)
- [ ] Upper bound on nodes visited per entry-point (suggested default: 150)

Update this document with the verified shapes once the snapshots exist.