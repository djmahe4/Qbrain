# The Complete Guide: Building a Business-Logic Aware DAST Platform on Qbrain

### Grounding on Context-Aware DAST, AST Knowledge Graphs via `codebase-memory-mcp`, Obsidian Vault RAG Sanitation, Local Ollama Reasoning, Sandboxed Execution, and Continuous DVWA Benchmarking

This document consolidates everything researched into one grounded, self-contained guide. It explicitly grounds the platform on **Business-Logic Aware Dynamic Application Security Testing (Context-Aware DAST)** powered by local **Agentic AI models via Ollama**, **Obsidian Vault RAG Sanitation & State Pruning**, `codebase-memory-mcp` knowledge graphs, Qbrain's business-rule mapper, **isolated Docker container sandboxing**, and **continuous DVWA benchmarking**.

---

## 1. Glossary (read this first if any term below is unfamiliar)

| Term | Plain-language definition |
|---|---|
| **Vulnerability** | A flaw in code or configuration that lets an attacker do something they shouldn't (read data they don't own, run commands, escalate privileges) |
| **CWE** | "Common Weakness Enumeration" — MITRE's standard numbered catalog of vulnerability *types* (e.g. CWE-89 = SQL Injection). It classifies the *kind* of bug. |
| **CVE** | "Common Vulnerabilities and Exposures" — a specific, real, publicly-disclosed vulnerability instance in a specific product (e.g. CVE-2025-14847). CWE is the category; CVE is the individual case. |
| **SAST** | Static Application Security Testing — reads source code without running it, looking for risky patterns |
| **DAST** | Dynamic Application Security Testing — attacks a *running* application from the outside and observes real behavior |
| **IAST** | Interactive Application Security Testing — instruments a running app so findings are tied to real runtime behavior *and* exact source lines |
| **Context-Aware DAST** | Dynamic Application Security Testing that uses static AST knowledge (routes, parameter schemas, auth rules) to intelligently generate targeted business-logic tests instead of firing blind payloads |
| **Business Logic Flaw** | A flaw in application design or workflow state (e.g. BOLA, authorization bypass, step-skipping) where code executes as written but violates intended business constraints |
| **Obsidian Vault RAG** | Using the local Obsidian Vault (`.qbrain/`, `files/`, `behaviors/`, `rules/`) as Qbrain's structured markdown "working memory on disk" and local RAG retrieval store for Ollama LLMs |
| **RAG Feedback Loop** | A risk where unverified false positives written to the vault are re-read by the LLM in future scans as "ground truth", causing self-reinforcing hallucinations |
| **Superposition Quarantine** | Storing unverified hypotheses strictly in `.qbrain/*.sqlite` (`status: "SUPERPOSITION"`), preventing unproven findings from polluting the Obsidian Vault RAG index |
| **Behavior Pruning & Merging** | Merging parameter-variant branch notes (e.g., merging 104 branch files in `behaviors/` into canonical route behavior notes) to prevent vault overpopulation |
| **Qualified Wiki-Links** | Using explicit vault paths (e.g. `[[files/routes/orders.py.md#L42]]`) to eliminate path collisions between `files/`, `behaviors/`, and source directories |
| **DVWA Benchmarking** | Continuous ground-truth validation against Damn Vulnerable Web Application (DVWA) to empirically verify that DAST scenarios catch and prove real vulnerabilities |
| **Taint Analysis** | Tracking how untrusted data (e.g. something a user typed) flows through a program from where it enters (**source**) to where it's used dangerously (**sink**), and whether it passes through code that makes it safe along the way (**sanitizer**) |
| **AST** | Abstract Syntax Tree — a structured, tree-shaped representation of source code that a program can understand (instead of treating code as plain text) |
| **Entry Point** | A place where external, untrusted input enters your program — an HTTP route, a CLI argument, a file upload, etc. |
| **Reachability Filtering** | Only analyzing code that is actually reachable from an entry point, instead of every line in the repository — this is what makes large-scale analysis affordable |
| **LLM** | Large Language Model — the AI model (e.g. GPT, Claude, or a local Ollama model) that reads text/code and reasons about it |
| **Agent / Agentic AI** | An LLM wired into a loop where it can plan multiple steps, call tools via MCP, look at results, and decide what to do next on its own — as opposed to a single one-shot question and answer |
| **MCP (Model Context Protocol)** | An open standard (created by Anthropic) that lets an LLM agent call external tools (like "search this codebase" or "run this scanner") through a common interface |
| **`codebase-memory-mcp`** | High-performance C / Tree-Sitter code intelligence engine (by `deusdata`) that builds a persistent knowledge graph of codebases to provide fast structural queries and AST analysis |
| **Ollama** | Free, open-source software that runs LLMs entirely on your own machine (no cloud, no API cost, no data leaving your network) |
| **Hallucination** | When an LLM confidently states something false — e.g. claiming a vulnerability exists when it doesn't, or citing a line number that isn't real |
| **Context Window** | The maximum amount of text an LLM can "see" at once; smaller/local models generally have smaller, more easily overwhelmed context windows |
| **RAG (Retrieval-Augmented Generation)** | Storing code as searchable embeddings in a vector database and retrieving only relevant pieces per prompt instead of stuffing the entire codebase into context |
| **Embedding / Vector Database** | A numeric representation of text/code capturing meaning; vector databases (e.g. ChromaDB) store embeddings to quickly retrieve similar code |
| **Cypher** | A declarative graph query language (originally Neo4j, used in `codebase-memory-mcp`) to query relationships like `CALLS`, `DEPENDS_ON`, `IMPLEMENTS`, or `HTTP_CALLS` |
| **Barnes-Hut / N-Body** | An algorithm that calculates gravitational forces among $N$ bodies; in Qbrain, used to measure coupling and entanglement between code symbols |
| **SAN Engine / Belief State** | State Adaptation Network tracking confidence scores across static discovery, agentic scenario generation, adversarial review, and DAST proof until a verdict collapses into `CONFIRMED` |
| **Evidence Lineage** | A recorded audit trail linking every confirmed vulnerability back to exact HTTP request/response logs, AST lines, and scanner output |
| **Adversarial Verification** | A second LLM pass that plays devil's advocate: it tries hard, from an attacker's realistic point of view, to prove a flagged issue is exploitable — or to disprove it |
| **Sandbox Environment** | An isolated, disposable Docker container pre-seeded with multi-tenant test data where generated DAST HTTP and Playwright test plans are executed safely |
| **Hybrid DAST Execution** | Dual-tier execution: fast-path raw HTTP (`httpx`) for REST APIs + browser-driven Playwright for complex SPAs, cookie/localStorage persistence, and UI-bound IDORs |
| **Playwright Bottleneck** | Headless browser testing adds high CPU/memory overhead; Qbrain mitigates this via browser pooling, asset interception (blocking images/fonts), and reserving Playwright strictly for stateful SPA/UI workflows |
| **IaC (Infrastructure as Code)** | Defining servers/cloud resources/networking as code files (Terraform, Kubernetes YAML, Docker Compose) instead of clicking through a cloud console |
| **Misconfiguration** | A security-relevant infrastructure setting that's wrong or too permissive (e.g. an S3 bucket set to public, an IAM role with admin access it doesn't need) |
| **BOLA / IDOR** | "Broken Object Level Authorization" — a business-logic vulnerability where a user can access another user's data just by changing an ID in a request |
| **Privilege Escalation** | Gaining more access/permissions than you're supposed to have |
| **State Machine Violation** | Executing API endpoints out of sequence (e.g. triggering `/api/checkout/confirm` without passing through `/api/payment/authorize`) |
| **Precision / Recall / F1 / FPR** | Standard evaluation metrics: Precision ($TP / (TP + FP)$), Recall ($TP / (TP + FN)$), F1 ($2 \cdot (P \cdot R) / (P + R)$), and False Positive Rate ($FP / (FP + TN)$) |
| **CASTLE & DVWA Benchmarks** | Standardized ground-truth vulnerability datasets used to benchmark detection accuracy and exploit reproduction rates |
| **Fine-Tuning** | Additional training on a smaller, specialized dataset to make a general-purpose model better at one specific task |

---

## 2. Background: Why Business-Logic DAST over Fully Agentic IAST?

> [!IMPORTANT]
> **Architectural Clarification: What Are We Building & How Does Sandboxing Work?**
>
> 1. **We are building 100% Context-Aware DAST (NOT IAST)**:
>    - **Why NOT IAST?** Interactive Application Security Testing requires injecting a runtime profiler/agent *inside* application memory (e.g. JVM agents or Python `sys.settrace`). This introduces severe execution latency, process deadlocks, memory leaks, and complex framework incompatibility — making it an operational bottleneck.
>    - **What is Context-Aware DAST?** Dynamic Application Security Testing attacks the app **externally via HTTP/DOM payloads**. Unlike traditional "blind" DAST, Qbrain uses **static AST code context** (extracted beforehand via `codebase-memory-mcp`) to inform the DAST generator *what routes exist, what roles guard them, what parameters represent user IDs, and what state sequences to test*.
>
> 2. **Does DAST Require Sandboxing? YES — Disposable Container Sandboxing**:
>    - Testing business-logic flaws (BOLA, IDOR, Auth bypass, state tampering) requires executing real HTTP write/update/delete operations and cross-tenant data requests.
>    - Running these dynamic tests against a live production database or developer workstation would corrupt real data.
>    - **The Qbrain Sandbox**: Spins up a disposable, isolated Docker container (`docker run --rm`) pre-seeded with multi-tenant test accounts (`User A` & `User B`). Once DAST test plan execution completes, the container is destroyed (`docker rm -f`), purging all mutated state.

Traditional application security tools suffer from two major limitations:
1. **Traditional SAST** generates high false-positive rates because it lacks runtime proof.
2. **Traditional DAST** is "dumb" — it fires generic SQLi/XSS fuzzing strings at endpoints without understanding application context, roles, state machines, or business rules.

**The Fully Agentic IAST Bottleneck**: Attempting to solve this by building a fully autonomous, agent-driven IAST system introduces severe operational bottlenecks:
- Multi-agent runtime loops hang or deadlock when parsing asynchronous events.
- Heavy process instrumentation introduces significant execution latency.
- Local LLMs hallucinate complex runtime states when given raw, unconstrained agent loops inside runtime memory.

**The Qbrain Solution: Context-Aware DAST with Agentic AI Reasoning**: Qbrain grounds its design on **Business-Logic Aware DAST**. Instead of running an agent inside runtime memory (IAST), Qbrain uses **static AST knowledge** (extracted via `codebase-memory-mcp`) to inform **dynamic testing (DAST)**. Local Agentic AI models (via Ollama) use MCP tools to navigate the static graph, understand what endpoints exist, what roles guard them, what parameters represent user IDs, and what state sequences are expected. The Agentic AI then drafts targeted business-logic DAST tests executed against an isolated sandbox container.

---

## 3. What we ARE building vs. what we are NOT building

| We ARE building | We are NOT building |
|---|---|
| A **Business-Logic Aware DAST** engine that uses AST graph context to generate targeted BOLA, Auth, and State-machine tests | A fully agentic IAST system requiring deep runtime process instrumentation and multi-agent execution loops |
| A hybrid pipeline: `codebase-memory-mcp` (AST graph) + `business_logic_mapper.py` (rule extraction) + local Ollama Agentic AI reasoning | A "dumb" DAST scanner that fires generic fuzzing payloads at random URL query strings |
| **Obsidian Vault RAG Sanitation & Quarantine**: gating unverified LLM hypotheses in SQLite (`SUPERPOSITION`) so the vault RAG never feeds hallucinations back to the LLM | Writing unverified hypotheses directly into RAG context markdown files, triggering self-reinforcing hallucination loops |
| **AST Behavior Merging & Pruning**: merging parameter-variant branch notes to prevent `behaviors/` vault overpopulation | Generating hundreds of redundant branch notes that pollute RAG retrieval |
| **Continuous DVWA Benchmarking**: continuously validating the DAST pipeline against DVWA to measure Precision, Recall, and F1 | Relying on unverified demos without ground-truth benchmark testing |
| **Sandboxed Dynamic Verification (Hybrid `httpx` + Playwright)**: executing raw HTTP or browser-driven tests against disposable test instances to prove business logic bypasses | A static-only tool that prints LLM opinions without running an exploit |
| A platform powered by **local Ollama models** for DAST scenario drafting, adversarial verification, and response triage | A cloud-only tool that leaks proprietary application code to external APIs |
| An extension of the **existing Qbrain codebase** — leveraging [indexer.py](https://github.com/djmahe4/Qbrain/tree/main/brain/indexer.py), [business_logic_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/business_logic_mapper.py), [taint_classifier.py](https://github.com/djmahe4/Qbrain/tree/main/brain/taint_classifier.py), [san_engine.py](https://github.com/djmahe4/Qbrain/tree/main/brain/san_engine.py), and [evidence_store.py](https://github.com/djmahe4/Qbrain/tree/main/brain/evidence_store.py) | A rewrite of Qbrain from scratch |

---

## 4. The Business-Logic DAST Pipeline, Step by Step

```text
 ┌────────────────┐     ┌──────────────────────┐     ┌────────────────────────┐
 │ AST Repository │ ──> │  codebase-memory-mcp │ ──> │ Business Logic Mapper  │
 │  (Source Code) │     │ (Graph & Entrypoints)│     │(Auth, Schema, Rules)   │
 └────────────────┘     └──────────────────────┘     └───────────┬────────────┘
                                                                 │
                                                                 ▼
 ┌────────────────┐     ┌──────────────────────┐     ┌────────────────────────┐
 │ Verified DAST  │ <── │ Sandboxed Execution  │ <── │ Clean Obsidian Vault + │
 │ Finding Report │     │ (httpx / Playwright) │     │ Local Ollama Agent AI  │
 └────────────────┘     └──────────────────────┘     └────────────────────────┘
```

1. **AST & Route Mapping** — [indexer.py](https://github.com/djmahe4/Qbrain/tree/main/brain/indexer.py) uses `codebase-memory-mcp` to index application routes, parameters, and entrypoints into a property graph.
2. **Business Rule & Taint Extraction** — [business_logic_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/business_logic_mapper.py) and [taint_classifier.py](https://github.com/djmahe4/Qbrain/tree/main/brain/taint_classifier.py) classify route authorization requirements, validation schemas, and sensitive parameters (`USER_ID`, `ROLE`, `ACCOUNT_NUM`).
3. **Obsidian Vault Clean Sync & Pruning** — [librarian.py](https://github.com/djmahe4/Qbrain/tree/main/brain/librarian.py) merges parameter-variant branches and writes canonical structural notes to the Obsidian Vault (`files/`, `behaviors/`, `rules/`), forming Ollama's local markdown RAG store.
4. **Agentic DAST Test Plan Generation** — The local Ollama Agent (using `qwen2.5-coder`) inspects the clean Obsidian Vault RAG and AST graph via MCP tools to draft targeted test cases for BOLA, Auth Bypass, and State Machine Violations.
5. **Adversarial Pass (Devil's Advocate)** — A second skeptical agent pass reviews the drafted scenario to verify victim $\neq$ attacker and ensure mandatory session guards aren't missed. Unconfirmed hypotheses remain quarantined in SQLite (`SUPERPOSITION`).
6. **Hybrid Sandboxed DAST Execution** — Spins up a disposable Docker container pre-seeded with multi-tenant test accounts. Runs raw `httpx` for REST APIs, or routes through Playwright headless browser for complex SPAs, cookie/localStorage persistence, and UI-bound IDORs.
7. **Belief State Collapse & Evidence Lineage** — [san_engine.py](https://github.com/djmahe4/Qbrain/tree/main/brain/san_engine.py) updates the finding's confidence score. If HTTP or DOM execution confirms unauthorized data access, the finding collapses to `CONFIRMED` and logs to [evidence_store.py](https://github.com/djmahe4/Qbrain/tree/main/brain/evidence_store.py).
8. **Reporting & Verified Obsidian Sync** — ONLY `CONFIRMED` findings are written to the public Obsidian vault under `rules/vulnerabilities.md` via [narrative_api.py](https://github.com/djmahe4/Qbrain/tree/main/brain/narrative_api.py).

---

## 5. Worked Example: Context-Aware DAST with Agentic AI

**Scenario**: A Flask route `/api/user/<id>/invoice` reads a database record by `id` with no ownership check, and the app's Terraform config attaches an overly broad S3 read policy to the same service.

| Step | Component / Agent | Action |
|---|---|---|
| 1 | `entrypoint_finder.py` | Detects `/api/user/<id>/invoice` as an externally-reachable Flask route |
| 2 | `systemic_auditor.py` | Traces `id` from the URL parameter into the database query function using AST taint propagation |
| 3 | `infra_scanner.py` (new) | Separately flags the Terraform file: the ECS task role attached to this service has `s3:GetObject` on `*` (all buckets), not just its own |
| 4 | [dependency_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/dependency_mapper.py) | Notices the route's code references the same S3 bucket name that appears in the Terraform output — this is the **link** |
| 5 | **Agent (Ollama + Obsidian RAG)** | Reads the route note and business rule from the Obsidian Vault (`files/routes.md`). It reasons: "the ID isn't checked against the logged-in user, and the S3 role is broader than needed — this could let user A read user B's invoice AND any object in the bucket." It drafts a structured finding with CWE-639 (BOLA) |
| 6 | **Agent ("Verifier" role, adversarial pass)** | Given the same evidence, actively tries to argue this is *not* exploitable: is there a session check elsewhere? It must attempt at least two different ways to disprove it, ensuring victim $\neq$ attacker. Unconfirmed state is kept in `.qbrain/*.sqlite` quarantine. |
| 7 | **Dynamic Verifier (Sandboxed DAST)** | Spins up a minimal Docker copy of the route with seeded users, generates a script that logs in as User A and requests User B's invoice ID, runs it, and checks whether User B's real data came back |
| 8 | [evidence_store.py](https://github.com/djmahe4/Qbrain/tree/main/brain/evidence_store.py) + [san_engine.py](https://github.com/djmahe4/Qbrain/tree/main/brain/san_engine.py) | Records every step; belief state collapses to `CONFIRMED` only because the sandbox step returned real leaked data — not because the LLM merely said so |
| 9 | [narrative_api.py](https://github.com/djmahe4/Qbrain/tree/main/brain/narrative_api.py) | Turns the full evidence chain into a human-readable report with exact HTTP payloads and proof logs written to Obsidian Vault `rules/vulnerabilities.md` |

---

## 6. `codebase-memory-mcp` — Deep Dive & Implementation in Qbrain

### 6.1 What is `codebase-memory-mcp`?

`codebase-memory-mcp` (developed by `deusdata`) is an open-source, high-performance code intelligence engine written in C with vendored **Tree-Sitter grammars covering 158 programming languages**. It parses repositories into a persistent SQLite property graph:
- **Nodes**: `File`, `Module`, `Class`, `Function`, `Variable`, `Entrypoint`, `HTTPRoute`, `ADR`.
- **Edges**: `DEPENDS_ON`, `CALLS`, `IMPLEMENTS`, `BUSINESS_RULE`, `SEMANTIC_GRAVITY`, `HTTP_CALLS`.

### 6.2 Complete Native MCP Tool Registry (14 Tools)

```text
                          ┌──────────────────────────┐
                          │   codebase-memory-mcp    │
                          └────────────┬─────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
   [1. Indexing]                 [2. Querying]                 [3. Analysis]
  - index_repository            - search_graph                - get_architecture
  - list_projects               - trace_path / trace_call_path- detect_changes
  - delete_project              - query_graph                 - manage_adr
  - index_status                - get_graph_schema            - ingest_traces
                                - get_code_snippet
                                - search_code
                                - list_directory
```

#### Category 1: Indexing Lifecycle
1. **`index_repository`**: Indexes source code into the SQLite graph database. Supports full, moderate, fast, and watch modes.
2. **`list_projects`**: Lists indexed workspaces and node/edge metrics across virtual environments.
3. **`delete_project`**: Purges a target project and associated graph data.
4. **`index_status`**: Returns real-time indexing status, worker queue lengths, and unparseable file warnings.

#### Category 2: Querying & Graph Traversal
5. **`search_graph`**: Structured search by symbol label (`Function`, `Class`), regex pattern, and degree filters.
6. **`trace_path` / `trace_call_path`**: BFS traversal of call chains (inbound caller tracing or outbound dependency expansion).
7. **`query_graph`**: Executes Cypher-like declarative graph queries over the SQLite property graph.
8. **`get_graph_schema`**: Returns node types, relationship definitions, edge properties, and schema statistics.
9. **`get_code_snippet`**: Retrieves exact source code definitions with surrounding context lines.
10. **`search_code`**: Fast text/regex search across indexed code snippets.
11. **`list_directory`**: Navigates file trees directly from database schemas.

#### Category 3: Analysis & Architecture Governance
12. **`get_architecture`**: Summarizes codebase layout, component layers, entrypoints, API routes, and hotspots.
13. **`detect_changes`**: Analyzes git diffs against the graph to compute modified symbols and impacted callers.
14. **`manage_adr`**: Complete CRUD management for Architecture Decision Records (ADRs).
15. **`ingest_traces`**: Ingests runtime trace logs to dynamically validate `HTTP_CALLS` and runtime call edges.

---

### 6.3 Qbrain Subprocess Security & Command Wrapper (`_run_cli`)

Qbrain wraps `codebase-memory-mcp` via the `Indexer` class in [brain/indexer.py](https://github.com/djmahe4/Qbrain/tree/main/brain/indexer.py#L42-L113) with process security controls:
- **Binary Resolution**: Resolves binary executable paths from `config.cbm_binary` or venv `bin/Scripts`.
- **Whitelist Verification**: Restricts binary names to allowed executables (`codebase-memory-mcp`, `cbm-cli`, `qbrain-helper`) to mitigate command injection (CWE-78).
- **Execution Isolation**: Runs commands via subprocess with JSON payloads (`codebase-memory-mcp cli <tool_name> '<json_args>'`).
- **Timeout Protection**: Sets a 120-second timeout to prevent process hangs (CWE-400).

```python
# Snippet from brain/indexer.py showing the secure CLI execution wrapper
def _run_cli(self, tool_name: str, args: Dict[str, Any]) -> str:
    binary = self.config.cbm_binary
    args_str = json.dumps(args)
    cmd = [exec_binary, "cli", tool_name, args_str]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
    return result.stdout.strip()
```

---

### 6.4 How Qbrain Modules Consume `codebase-memory-mcp`

| Qbrain Module | `codebase-memory-mcp` Tool | How it is used in Qbrain |
|---|---|---|
| [indexer.py](https://github.com/djmahe4/Qbrain/tree/main/brain/indexer.py) | `index_repository`, `list_projects` | Executed during `qbrain index` to build the AST property graph. |
| [business_logic_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/business_logic_mapper.py) | `get_functions_with_docstrings`, `get_code_snippet` | Scans function docstrings and AST snippets to extract business rules (`authorization`, `validation`). |
| [git_watcher.py](https://github.com/djmahe4/Qbrain/tree/main/brain/git_watcher.py) | `detect_changes` | Tracks diff modifications to re-evaluate affected DAST test scenarios. |
| [dependency_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/dependency_mapper.py) | `query_graph`, `trace_path` | Runs Cypher queries (`MATCH (a)-[:DEPENDS_ON]->(b)`) to build API dependency trees. |
| [systemic_auditor.py](https://github.com/djmahe4/Qbrain/tree/main/brain/systemic_auditor.py) | `trace_call_path`, `get_code_snippet` | Traces user input sources to sensitive database/file sinks. |
| [librarian.py](https://github.com/djmahe4/Qbrain/tree/main/brain/librarian.py) | `get_architecture`, `manage_adr` | Synthesizes codebase state into Obsidian Vault markdown pages, Mermaid call graphs, and ADR registers. |
| [cli.py](https://github.com/djmahe4/Qbrain/tree/main/brain/cli.py) | All 14 tools | Exposes user commands (`qbrain index`, `qbrain watch`, `qbrain query`, `qbrain deps`, `qbrain rules`, `qbrain adr`). |

---

## 7. Core Architectural Insights & Physical Engine in Qbrain

### 7.1 Dual-Persistence & Obsidian Vault RAG Architecture
Qbrain splits state storage cleanly:
1. **SQLite Mind Database** (`.qbrain/qbrain-mind-{project}.sqlite`): Managed via [persistence_manager.py](https://github.com/djmahe4/Qbrain/tree/main/brain/persistence_manager.py), storing node states, call graphs, taint labels, and belief scores.
2. **Obsidian Knowledge Vault (RAG Store & Working Memory)**: Managed via [librarian.py](https://github.com/djmahe4/Qbrain/tree/main/brain/librarian.py), rendering Markdown notes, Mermaid state machine charts, and backlinks under `files/`, `behaviors/`, and `rules/`.

```text
  ┌────────────────────────┐       ┌────────────────────────┐
  │  SQLite Mind Database  │ <───> │ Obsidian Vault (RAG)   │ <───> Local Ollama Agent
  │ (.qbrain/*.sqlite)     │       │ (Markdown/Mermaid/Vault)│       (Tool-Calling Loop)
  └────────────────────────┘       └────────────────────────┘
```

**Why Obsidian Vault is Essential**:
- **Working Memory on Disk**: Local Ollama models operate with limited context windows. Storing indexed code symbols, docstring genomes, and state machines as Obsidian markdown notes provides persistent "working memory on disk".
- **Local RAG Retrieval**: Ollama queries the vault using local vector embeddings (`sentence-transformers`) to fetch only the specific notes relevant to a given route.
- **Human Transparency**: Developers open the Obsidian Vault to visually navigate Mermaid call graphs, inspect business rules, and review verified vulnerability reports.

### 7.2 Business Logic Rule Extraction
[business_logic_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/business_logic_mapper.py) extracts typed `BusinessRule` objects from AST docstrings and technical code markers:
- `validation`: Schema parsing, range checks, null checks.
- `authorization`: Ownership checks, role requirements, permission guards.
- `computation`: Math operations, balance checks, calculations.
- `io`: Database queries, file writes, network calls.

### 7.3 Barnes-Hut N-Body Gravity & Entanglement Engine
Qbrain models code relationships using gravitational physics in [quantum_scorer.py](https://github.com/djmahe4/Qbrain/tree/main/brain/quantum_scorer.py):
$$F = G \frac{m_1 m_2}{r^2}$$
Symbols with strong call frequency or shared taint flows experience high "semantic gravity", identifying critical business logic hotspots.

### 7.4 Belief-State Collapse & Evidence Lineage
In [san_engine.py](https://github.com/djmahe4/Qbrain/tree/main/brain/san_engine.py) and [evidence_store.py](https://github.com/djmahe4/Qbrain/tree/main/brain/evidence_store.py), DAST findings transition through belief states (`SUPERPOSITION` $\rightarrow$ `ACTIVE`). A finding collapses to `CONFIRMED` only when dynamic HTTP execution confirms an unauthorized response.

---

## 8. Sandboxed DAST Execution Architecture & Hybrid (httpx + Playwright) Engine

To move from static hypothesis generation to empirical proof without endangering host machines, Qbrain implements a dedicated **Hybrid Sandboxed DAST Execution Subsystem**:

```text
 ┌──────────────────────┐      ┌─────────────────────────────────────────────────┐
 │ DAST Test Plan JSON  │ ───> │ Sandboxed Executor (dynamic_verifier)           │
 │(Method, Route, Body) │      │  ├── Fast Path: Plain httpx Runner              │
 └──────────────────────┘      │  └── Stateful Path: Playwright Browser Runner   │
                               └────────────────────────┬────────────────────────┘
                                                        │
                                                        ▼
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ Isolated Docker Container (qbrain-dast-sandbox)                                │
 │  ├── Target Application Instance & Seeded Multi-Tenant DB (User A / User B)  │
 │  ├── Network Isolation (--net=bridge, no outbound internet)                  │
 │  └── Resource Caps (CPU: 1 core, RAM: 512MB, Read-Only Root FS)               │
 └──────────────────────────────────────┬────────────────────────────────────────┘
                                        │
                                        ▼
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ HTTP / DOM Response Assertion Engine                                          │
 │  ├── Status Code & Response Payload Inspection                                │
 │  ├── Playwright Cookie & localStorage State Interception                      │
 │  └── Output Evidence Logging -> evidence_store.py                             │
 └───────────────────────────────────────────────────────────────────────────────┘
```

### 8.1 The Playwright Bottleneck vs. The Need for Browser-Driven DAST

While raw HTTP clients (`httpx` / `requests`) execute extremely fast (~10ms per test), **raw HTTP alone cannot catch complex IDORs or persistence-based flaws in modern web applications**:
- Single-Page Applications (React, Vue, Next.js) store session state in `localStorage`, `sessionStorage`, or encrypted HTTP-only cookies managed client-side.
- Modern frameworks use dynamic CSRF tokens, client-side route guards, or complex OAuth PKCE state exchanges that fail under static raw HTTP replays.
- Stored/Persisted IDORs (e.g. User A uploads a malicious profile setting or persistent payload that triggers when User B views the UI) require full DOM rendering and script execution to detect.

**However, Playwright is a major performance bottleneck**: launching headless Chromium instances introduces high startup overhead (1–2 seconds per launch) and high CPU/RAM usage.

### 8.2 Qbrain's Dual-Tier Hybrid Execution Strategy

To eliminate the Playwright performance bottleneck while maintaining 100% testing fidelity, Qbrain implements a **Dual-Tier Hybrid Executor**:

```text
                              [DAST Test Scenario]
                                       │
                      Is the endpoint a headless REST API?
                                  /         \
                             YES /           \ NO (SPA / Cookie Auth / UI IDOR)
                                /             \
                   ┌───────────▼───────────┐ ┌─▼─────────────────────────────┐
                   │ Tier 1: Fast httpx    │ │ Tier 2: Playwright Headless   │
                   │ (10ms / request)      │ │ (Browser Pool & Resource Intercept)│
                   └───────────────────────┘ └───────────────────────────────┘
```

1. **Tier 1: Fast-Path Raw HTTP (`httpx`)**:
   - Used for stateless REST APIs, JSON webhooks, microservices, and direct parameter-tampering tests.
   - Executes in milliseconds with minimal resource footprint.

2. **Tier 2: Playwright Headless Browser Runner (Optimized)**:
   - Used exclusively for UI-bound routes, Single-Page Applications, cookie/localStorage session state, and persistent IDORs.
   - **Playwright Bottleneck Mitigations**:
     - **Browser Pooling**: Maintains a pre-warmed pool of headless Chromium browser contexts across tests to eliminate startup latency.
     - **Asset Interception**: Intercepts and aborts image, font, and CSS downloads (`route.abort()`), reducing page load overhead by 80%.
     - **Context Reuse**: Reuses authenticated browser contexts for User A and User B across test runs rather than re-logging in per test.

---

### 8.3 Docker Container Sandbox Lifecycle
1. **Provisioning**: Spins up a clean Docker container instance of the application repo (`docker run --rm`).
2. **Database Seeding**: Injects standardized test fixtures containing multi-tenant test accounts (`User A`, `User B`, `Admin`).
3. **Execution Isolation**: Restricts container capabilities (`--net=bridge`, `--read-only` root FS, `--cpus=1.0 --memory=512m`).
4. **Hybrid Execution**: Runs `httpx` for raw REST endpoints; routes through the Playwright browser pool for SPA/UI-bound routes.
5. **Response & DOM Assertion**: Asserts whether unauthorized cross-tenant data appeared in raw HTTP JSON or rendered Playwright DOM elements.
6. **Teardown**: Wipes container state (`docker rm -f`).

---

## 9. Vault Sanitation Architecture: Eliminating RAG Feedback Loops & Overpopulation

As revealed when evaluating real codebases (e.g. DVWA generating 104 individual branch notes in `behaviors/`), an uncurated Obsidian Vault introduces severe AI failure modes.

### 9.1 The Threat: Self-Reinforcing LLM RAG Feedback Loops

If unverified hypotheses or false positives get written directly into markdown files in the Obsidian Vault (`vulnerabilities.md` or `rules/`), and local Ollama agents use the Obsidian Vault as a RAG context store for future prompts:
- **The Self-Reinforcing Hallucination Loop**: The LLM reads its own past false positives or hallucinations as "ground truth", compounding errors across scans.
- **Example**: In Scan 1, an unconstrained prompt claims `/api/user` has a BOLA vulnerability. If written to `rules/vulnerabilities.md`, in Scan 2, the LLM reads `vulnerabilities.md`, sees the entry, and declares: *"The Obsidian Vault confirms this route is vulnerable!"*

### 9.2 The Solution: Strict Superposition Quarantine (SAN Engine Gating)

To break this feedback loop, Qbrain enforces a strict **Read/Write Sanitation Gate**:

```text
 ┌──────────────────────────┐      Unverified Hypotheses      ┌──────────────────────────────────┐
 │ Scanner & Agent Output   │ ──────────────────────────────> │ SQLite Mind (.qbrain/*.sqlite)   │
 │ (Hypotheses & Traces)    │                                 │ [status: "SUPERPOSITION"]        │
 └──────────────────────────┘                                 │ (QUARANTINED FROM RAG retrieval) │
                                                              └────────────────┬─────────────────┘
                                                                               │
                                                                 Sandboxed DAST Confirmed Proof
                                                                               │
                                                                               ▼
 ┌──────────────────────────┐     Only Confirmed Findings     ┌──────────────────────────────────┐
 │ Obsidian Vault RAG Index │ <────────────────────────────── │ rules/vulnerabilities.md         │
 │ (Available to LLM Prompts)│                                 │ [status: "CONFIRMED"]            │
 └──────────────────────────┘                                 └──────────────────────────────────┘
```

1. **Quarantine Zone (`.qbrain/*.sqlite`)**: All raw scanner outputs, unverified LLM hypotheses, and intermediate observations are stored strictly in the `.qbrain` SQLite database under `status: "SUPERPOSITION"`.
2. **RAG Exclusion**: The RAG retrieval pipeline **strictly ignores** `SUPERPOSITION` records.
3. **The Confirmation Gate**: A finding is **ONLY** written to `vulnerabilities.md` or exported to public Obsidian notes when it transitions to `status: "CONFIRMED"` via empirical Sandboxed DAST execution (HTTP 200 payload leak or Playwright DOM proof).

### 9.3 Behavior Folder Overpopulation & State Machine Merging

Emitting a separate markdown note for every conditional branch / parameter variant floods `behaviors/` with noise (e.g., 104 DVWA branch notes like `Sqli_Index_Dvwasecuritylevelget___medium_else_bran_b7755d.md`). This dilutes RAG context retrieval.

**Qbrain's AST State Pruning & Merging**:
[librarian.py](https://github.com/djmahe4/Qbrain/tree/main/brain/librarian.py) implements AST state-merging:
- **Canonical Merging**: Merges parameter-variant branch notes (`default`, `low`, `medium`, `high`) into a single canonical route behavior note (`behaviors/sqli_index.md`).
- **Pruning Boilerplate**: Prunes synthetic HTML redirectors and trivial return branches.
- **High-Arity Focus**: Restricts Mermaid state machine generation to high-arity business logic routes.

### 9.4 Eliminating Wiki-Link Collisions via Qualified Vault Paths

Obsidian wiki-links without explicit path qualifiers (e.g. `[[index_php]]`) cause collision errors when files share names across `files/`, `behaviors/`, `symbols/`, or source repository folders:
- **Qualified Path Standard**: Qbrain mandates fully qualified relative/absolute vault paths for all generated wiki-links:
  - Use `[[files/vulnerabilities/sqli/index.php.md]]` instead of `[[index.php]]`.
  - Use `[[behaviors/sqli_index.md#State-Machine]]` instead of `[[sqli_index]]`.
  - Use clickable local file links `[sqli/index.php](file:///path/to/dvwa/vulnerabilities/sqli/index.php#L42)` for precise source code line targets.

---

## 10. Context Awareness & Anti-Hallucination in DAST

To prevent local LLMs from hallucinating invalid vulnerabilities, Qbrain enforces strict structural constraints:

| Technique | Why it works | Implementation in Qbrain |
|---|---|---|
| **AST Reachability Filtering** | Prunes unexposed internal functions before generating DAST scenarios | [entrypoint_finder.py](https://github.com/djmahe4/Qbrain/tree/main/brain/entrypoint_finder.py) |
| **AST-Aware Chunking** | Preserves complete function boundaries via Tree-Sitter grammars | `codebase-memory-mcp` |
| **Sanitized Obsidian Vault RAG** | Provides clean, non-polluted Markdown notes of routes and rules to the LLM | [librarian.py](https://github.com/djmahe4/Qbrain/tree/main/brain/librarian.py) + Section 9 |
| **Structured Test Plan Schemas** | Forces the scenario generator to emit strict JSON DAST schemas (method, path, headers, body, expected status) | Qbrain DAST Generator |
| **Proof by Hybrid Execution** | Findings are declared valid ONLY if real sandboxed `httpx` or Playwright DOM execution returns observable unauthorized data | Sandboxed DAST Executor (Section 8) |
| **Victim != Attacker Rule** | Rejects DAST tests where an authenticated user only affects their own data | Adversarial Verifier |
| **Evidence Lineage Tracking** | Links confirmed bugs to raw HTTP request/response payloads and Playwright DOM snapshots | [evidence_store.py](https://github.com/djmahe4/Qbrain/tree/main/brain/evidence_store.py) |

---

## 11. Ollama Integration — Local Agentic AI Architecture

### 11.1 The Negative Result (Snitch Paper) & Why Agentic MCP Loops Are Mandatory

A 2026 empirical study ([arXiv:2606.11672](https://arxiv.org/html/2606.11672v1)) evaluated local LLMs (Ollama-hosted `gemma3`, `llama3.1`, `qwen2.5`) given raw, unconstrained prompts to find software bugs. The results were clear: **49–90% false-positive rates and recall under 0.25** — performing far worse than deterministic tools while consuming massive compute.

**Why Agentic Loops Succeed Where Raw Prompts Fail**:
A local model given a blank prompt tries to guess vulnerabilities. In Qbrain, local Ollama models run inside an **Agentic Tool-Calling Loop** (via MCP) using the sanitized Obsidian Vault RAG:

```text
 ┌────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
 │ Goal Prompt    │ ──> │ Local Ollama Agent   │ ──> │ Calls MCP / Vault RAG│
 │ (Analyze Route)│     │ (qwen2.5-coder:14b)  │     │ (get_code_snippet)   │
 └────────────────┘     └──────────▲───────────┘     └──────────┬───────────┘
                                   │                            │
                                   └────── Observes Result ─────┘
```

The agent is never asked to search blindly. It receives pre-filtered reachable routes, reads clean Obsidian Vault notes, calls `search_graph` or `get_code_snippet` to inspect context on-demand, and formulates structured DAST hypotheses.

### 11.2 What Local Ollama Models Should — and Shouldn't — Do

| Task | Should Ollama do it? | Why |
|---|---|---|
| Raw vulnerability detection from a blank prompt | **No** | Proven to fail with 49–90% false positives (Section 11.1) |
| Exposure classification on pre-filtered, reachable code | **Yes** | Scope is narrowed by deterministic AST tools; the model answers a bounded question |
| Drafting correlated code+infra DAST hypotheses | **Yes** | Reasons over structured evidence produced by scanners, `codebase-memory-mcp`, and Obsidian Vault RAG |
| Writing exploit/PoC DAST HTTP & Playwright scripts | **Yes, with retry-on-error** | Code generation is a strength of local code-tuned models; failed scripts get retried with error logs |
| Adversarial / Skeptical verification | **Yes** | Benefits from multi-pass reasoning (testing victim $\neq$ attacker) |
| Context compression & trace summarization | **Yes, even a small model** | Summarization runs efficiently on small 3B models |

---

### 11.3 Recommended 3-Tier Model Architecture

To balance local GPU memory, execution speed, and reasoning depth, Qbrain adopts a 3-tier Ollama model architecture (adapted from FuzzingBrain V2):

| Tier | Example Ollama Models | Primary Duty in Qbrain |
|---|---|---|
| **Tier 1: Utility** (Fast & Light) | `llama3.2:3b`, `qwen2.5:3b` | Context compression, log summarization, deduplication |
| **Tier 2: Main Reasoning** (Code-Tuned) | `qwen2.5-coder:14b`, `deepseek-coder-v2:16b` | Route exposure classification, DAST HTTP & Playwright scenario drafting, PoC script generation |
| **Tier 3: Escalation** (Deep Reasoning) | Claude 3.5 Sonnet (API) or `qwen2.5-coder:32b` | Adversarial verification pass for ambiguous or high-severity BOLA candidates |

---

### 11.4 Open-Source Ecosystem & Reference Implementations

Qbrain borrows proven agentic patterns from leading open-source security projects:

| Project / Benchmark | Core Pattern Borrowed by Qbrain |
|---|---|
| [OpenAnt](https://github.com/knostic/OpenAnt) | 6-stage detect → adversarial-verify → dynamic verify pipeline design; victim != attacker rule |
| [FuzzingBrain V2](https://arxiv.org/html/2605.21779v1) | Multi-agent Generator/Verifier role split, MCP tool-calling loop, context compressor agent |
| [bhavsec/autopentest-ai](https://github.com/bhavsec/autopentest-ai) | Scout/Analyzer/Exploiter/Reporter architecture, **native Ollama offline mode** integration |
| [lintsinghua/DeepAudit](https://github.com/lintsinghua/DeepAudit) | Tree-Sitter AST code indexing + ChromaDB RAG vector search with **Ollama embeddings** |
| VULPO / [ContextVul](https://arxiv.org/html/2511.11896v3) | Fine-tuned 4B model benchmarking for context-aware vulnerability reasoning |
| OASIS (`github.com/psyray/oasis`) | Two-phase Ollama scanner with LangGraph multi-model orchestration |
| `protectai/vulnhuntr` | Zero-shot call-chain analysis reference |
| CASTLE Benchmark, DVWA | Ground-truth testbeds for precision/recall evaluation |

---

## 12. Continuous DVWA Benchmarking & Validation Methodology

### 12.1 Why Continuous DVWA Benchmarking Grounding is Mandatory

Building a security scanning platform without continuous empirical testing against a ground-truth benchmark leads to unverified claims. **DVWA (Damn Vulnerable Web Application)** serves as Qbrain's continuous ground-truth CI/CD target.

During development, Team 6 continuously executes the Qbrain pipeline against DVWA to verify that:
1. AST & entrypoint mapping correctly locates DVWA's vulnerable routes (e.g. `/vulnerabilities/fi/`, `/vulnerabilities/sqli/`, `/vulnerabilities/id/`).
2. Ollama DAST scenario generators correctly draft cross-tenant BOLA and authorization payloads.
3. Sandboxed dynamic execution successfully reproduces vulnerabilities, achieving target Precision ($>95\%$) and Recall ($>80\%$).

---

### 12.2 Evaluation Corpora

Evaluation is conducted across three ground-truth target suites:
1. **DVWA (Damn Vulnerable Web Application)**: Primary continuous CI/CD ground-truth benchmark for web application vulnerabilities (BOLA, Auth Bypass, SQLi, Command Injection).
2. **CASTLE Benchmark**: Standardized benchmark dataset ([TASE 2025](https://ssvlab.github.io/lucasccordeiro/papers/tase2025.pdf)) evaluating static code analyzers and LLMs on real security flaws.
3. **Custom Business-Logic Testbed**: Synthetic corpus of 50 microservices containing 100 injected business-logic flaws (CWE-639 BOLA, CWE-862 Auth Bypass, State Machine violations) and 100 benign routes.

### 12.3 Quantitative Metrics & Mathematical Definitions

Qbrain measures five core detection metrics:

- **Precision (P):** The proportion of reported findings that represent real, exploitable vulnerabilities<br>**P = TP / (TP + FP)**

- **Recall (R):** The proportion of ground-truth vulnerabilities correctly caught by the pipeline<br>**R = TP / (TP + FN)**

- **F1-Score ($F_1$):** The harmonic mean balancing precision and recall<br>$$F_1 = 2 \cdot \frac{P \cdot R}{P + R}$$

- **False Positive Rate (FPR):** The frequency at which benign routes are incorrectly flagged<br>**FPR = FP / (FP + TN)**

- **Exploit Reproduction Rate:** The percentage of agent-drafted DAST hypotheses successfully reproduced in the Docker sandbox<br>**Reproduction Rate = (Sandboxed DAST Confirmed Findings / LLM Hypothesis Candidates) × 100%**

**Target:** > 75% based on OpenAnt empirical baselines.
---

### 12.4 Pipeline Verification Funnel Metrics

Qbrain tracks candidate filtering across four operational pipeline stages to prevent false-positive inflation:

```text
 Stage 1: AST Route Discovery (100% Candidates)
    │
    ▼
 Stage 2: Business Rule & Taint Filter (Prunes ~70% of safe routes)
    │
    ▼
 Stage 3: Agentic Adversarial Pass (Prunes ~60% of unexploitable hypotheses)
    │
    ▼
 Stage 4: Sandboxed DAST Proof (100% Precision on Confirmed Findings)
```

| Pipeline Stage | Target Input Scope | Expected Output Precision | Purpose |
|---|---|---|---|
| **Stage 1: AST Discovery** | Entire Repository (100% routes) | N/A | Maps entrypoints and parameter schemas via `codebase-memory-mcp`. |
| **Stage 2: Rule & Taint Filter** | Exposed Routes | Low (~25%) | Identifies routes with user input parameters touching sensitive sinks. |
| **Stage 3: Adversarial Pass** | Filtered Hypotheses | Moderate (~65%) | Skeptical agent pass verifies victim $\neq$ attacker and verifies session guards. |
| **Stage 4: Sandboxed DAST Proof** | Test Plans | **100% High Precision** | Sandboxed Docker `httpx` or Playwright DOM execution returns empirical proof. |

---

## 13. Team Split & 16-Week Implementation Plan

### 13.1 Team Structure (6 Sub-Teams, 10–15 People)

| Team | Focus Area | Key Deliverable | Qbrain Dependencies |
|---|---|---|---|
| **1. AST & Rule Extraction Team** | Static Context | AST graph indexing, docstring rule parsing | [indexer.py](https://github.com/djmahe4/Qbrain/tree/main/brain/indexer.py), [business_logic_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/business_logic_mapper.py) |
| **2. DAST Scenario Generator Team** | Test Planning | Generating BOLA, Auth Bypass, State Machine test plans via Ollama | [taint_classifier.py](https://github.com/djmahe4/Qbrain/tree/main/brain/taint_classifier.py), [dependency_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/dependency_mapper.py) |
| **3. Sandboxed Executor Team** | Dynamic Proof | Dual-tier hybrid runner (`httpx` + Playwright pool), Docker testbed setup | Docker (Section 8), `httpx`, Playwright |
| **4. Belief & Evidence Team** | Audit Lineage | Confidence scoring collapse, evidence logging | [san_engine.py](https://github.com/djmahe4/Qbrain/tree/main/brain/san_engine.py), [evidence_store.py](https://github.com/djmahe4/Qbrain/tree/main/brain/evidence_store.py) |
| **5. Obsidian Vault & CLI Team** | User Experience & RAG | Vault sync, RAG quarantine gating, AST state merging, Mermaid diagrams | [librarian.py](https://github.com/djmahe4/Qbrain/tree/main/brain/librarian.py), [cli.py](https://github.com/djmahe4/Qbrain/tree/main/brain/cli.py) |
| **6. Benchmarking & Quality Team** | Evaluation | Continuous DVWA benchmarking & CASTLE evaluation | Pytest, DVWA, CASTLE Benchmark (Section 12) |

### 13.2 16-Week Implementation Cadence

| Weeks | Phase | Core Deliverables |
|---|---|---|
| **Week 1** | **Contracts & Schemas** | Define DAST JSON schema (method, path, headers, body, expected status), agree on MCP interfaces. |
| **Weeks 2–4** | **AST & Rule Extraction** | Enhance [business_logic_mapper.py](https://github.com/djmahe4/Qbrain/tree/main/brain/business_logic_mapper.py) and [taint_classifier.py](https://github.com/djmahe4/Qbrain/tree/main/brain/taint_classifier.py). Prototype mock DAST test scenarios on DVWA. |
| **Weeks 5–8** | **DAST Generator & Sandbox** | Build Docker sandbox runner and hybrid `httpx` + Playwright executor (Section 8); implement Vault RAG Quarantine Gate (Section 9); integrate Ollama `qwen2.5-coder`. |
| **Weeks 9–12** | **Dynamic Verification & Lineage** | Connect HTTP/DOM execution output to [san_engine.py](https://github.com/djmahe4/Qbrain/tree/main/brain/san_engine.py) belief state collapse and [evidence_store.py](https://github.com/djmahe4/Qbrain/tree/main/brain/evidence_store.py). |
| **Weeks 13–14** | **End-to-End System Testing** | Run joint integration tests across DVWA and complex web application repos. |
| **Weeks 15–16** | **Benchmarking & Release** | Measure Precision/Recall/F1 against DVWA and CASTLE benchmarks (Section 12); publish v1.0. |

---

## 14. Consolidated References

## **Academic Papers:**
1. "SAST vs DAST vs IAST 2026: Developer Comparison Guide." https://www.securecodinghub.com/blog/iast-vs-dast-vs-sast-comparison-guide
2. Korda, N., Evron, G. "OpenAnt: LLM-Powered Vulnerability Discovery Through Code Decomposition, Adversarial Verification, and Dynamic Testing." arXiv:2606.19149, 2026. https://arxiv.org/html/2606.19149
3. Sheng, Z. et al. "FuzzingBrain V2: A Multi-Agent LLM System for Automated Vulnerability Discovery and Reproduction." arXiv:2605.21779, 2026. https://arxiv.org/html/2605.21779v1
4. "Can Open-Source LLM Agents Replace Static Application Security Testing (SAST) Tools?" arXiv:2606.11672, 2026. https://arxiv.org/html/2606.11672v1
5. Deng, G. et al. "PentestGPT: Evaluating and Harnessing LLMs for Automated Penetration Testing." USENIX Security 2024. https://www.usenix.org/conference/usenixsecurity24/presentation/deng
6. Wang, M. et al. "Anota: Identifying Business Logic Vulnerabilities via Annotation-Based Sanitization." NDSS Symposium 2026. https://arxiv.org/html/2512.20705v1
7. "LogicScan: An LLM-driven Framework for Detecting Business Logic Vulnerabilities in Smart Contracts." arXiv:2602.03271, 2026. https://arxiv.org/abs/2602.03271
8. "CASTLE: Benchmarking Dataset for Static Code Analyzers and LLMs in Vulnerability Detection." TASE 2025. https://ssvlab.github.io/lucasccordeiro/papers/tase2025.pdf

## **Open-Source Projects & Standards:**
9. `deusdata/codebase-memory-mcp` — High-performance C / Tree-Sitter code intelligence engine. https://github.com/deusdata/codebase-memory-mcp
10. `djmahe4/Qbrain` — Core codebase for context-aware security intelligence. https://github.com/djmahe4/Qbrain
11. `bhavsec/autopentest-ai` — Scout/Analyzer/Exploiter/Reporter architecture. https://github.com/bhavsec/autopentest-ai
12. CASTLE Benchmark. https://github.com/CASTLE-Benchmark/CASTLE-Benchmark
13. DVWA (Damn Vulnerable Web Application). https://github.com/digininja/DVWA
14. OWASP Top 10:2025 (#2 Security Misconfiguration, #1 Broken Access Control). https://owasp.org/Top10/2025/0x00_2025-Introduction/
