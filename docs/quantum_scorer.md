# quant-blm Quantum Scorer Documentation

This document describes the quantum scoring and N-body physics engine implemented in Phase 3 of the **Quantum Brain** (`quant-blm`).

## 1. Physics Model & Formulas

The physics simulation models codebase symbols as particles in a gravity field, using:
- **Mass Calculation**:
  `mass = 1.0 + complexity * 0.3 + sideEffects * 0.5 + (2.0 if isExported else 0.0)`
- **Gravitational Force (Attraction)**:
  `F_ij = G * (m_i * m_j) / (d_ij^2)` where `d_ij` is the semantic distance.
- **Repulsive Force (Anti-Collapse)**:
  `R_ij = k_repulse / d_ij`. This acts as Coulomb-like repulsion to prevent collapse into a single mathematical singularity.
- **Potential Energy**:
  `U_i = - sum G * (m_i * m_j) / d_ij`
- **Sigmoid Normalisation**:
  Normalises Potential Energy to `[0,1]` using a standard sigmoid function:
  `score = 1.0 - (1.0 / (1.0 + exp(-U / U_max)))`
- **Cluster Centrality**:
  Measures proximity to the local center of mass:
  `centrality = 1.0 / (1.0 + distance_to_center_of_mass)`

## 2. Barnes-Hut Quadtree (`QuadNode`)

For scaling simulations where functional count `N > 500`, the physics engine switches automatically to a **Barnes-Hut algorithm**:
- Divides 2D coordinate spaces into quadtree zones.
- Approximates distant forces by grouping sub-trees into single mass points.
- Reduces time complexity from $O(N^2)$ to $O(N \log N)$.
- **Stability**: Includes safeguards against `ZeroDivisionError` during normalization for small or singular graphs.


## 3. SQLite & Graph Synchronization

Updates properties on existing node instances in the SQLite "Mind" sidecar and writes semantic attraction boundaries to `codebase-memory-mcp`:
- **Internal Persistence (Mind)**: Primary store for `mass`, `potential_energy`, `business_score`, `cluster_centrality`, and `quantum_state`.
- **Graph Persistence (Graph)**: Best-effort write of physics metadata and `[SEMANTIC_GRAVITY {force: float}]` edges to represent mutual attraction.