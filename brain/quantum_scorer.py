import math
import random
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from brain.config import Config
from brain.indexer import Indexer
from brain.embedder import Embedder
from brain.logger import get_logger

logger = get_logger(__name__)


class FunctionNode:
    def __init__(self, name: str, embedding: np.ndarray, complexity: float = 0.0,
                 side_effects: float = 0.0, is_exported: bool = False, file: str = "", line: int = 0):
        self.name = name
        self.embedding = embedding
        self.complexity = complexity
        self.side_effects = side_effects
        self.is_exported = is_exported
        self.file = file
        self.line = line

        # Physics variables
        self.mass = self.compute_mass()
        self.position = [0.0, 0.0]
        self.velocity = [0.0, 0.0]
        self.potential_energy = 0.0
        self.business_score = 0.0
        self.cluster_centrality = 0.0
        self.quantum_state = "superposition"

    def compute_mass(self) -> float:
        """
        Mass formula: 1.0 + complexity*0.3 + sideEffects*0.5 + export*2.0
        """
        mass = 1.0
        mass += self.complexity * 0.3
        mass += self.side_effects * 0.5
        if self.is_exported:
            mass += 2.0
        return mass


class QuadNode:
    """A Quadtree node for Barnes-Hut N-body simulation in 2D space."""
    def __init__(self, boundary: Tuple[float, float, float, float]):
        # boundary is (x_min, y_min, x_max, y_max)
        self.boundary = boundary
        self.node: Optional[FunctionNode] = None
        self.children: Optional[List['QuadNode']] = None
        self.center_of_mass = [0.0, 0.0]
        self.total_mass = 0.0

    def insert(self, fn: FunctionNode) -> bool:
        # Check boundary
        x_min, y_min, x_max, y_max = self.boundary
        px, py = fn.position
        if not (x_min <= px <= x_max and y_min <= py <= y_max):
            return False

        if self.total_mass == 0.0:
            self.node = fn
            self.center_of_mass = [px, py]
            self.total_mass = fn.mass
            return True

        # If it's a leaf node containing a single node, we subdivide
        if self.children is None:
            if self.node is not None and self.node.name == fn.name:
                # Duplicate position or identical node, slightly nudge to prevent collision
                fn.position[0] += random.uniform(-1e-5, 1e-5)
                fn.position[1] += random.uniform(-1e-5, 1e-5)
                px, py = fn.position

            self.subdivide()
            if self.node is not None:
                old_node = self.node
                self.node = None
                for child in self.children:
                    if child.insert(old_node):
                        break

        # Insert new particle
        inserted = False
        for child in self.children:
            if child.insert(fn):
                inserted = True
                break

        # Update center of mass and total mass
        cx = (self.center_of_mass[0] * self.total_mass + px * fn.mass) / (self.total_mass + fn.mass)
        cy = (self.center_of_mass[1] * self.total_mass + py * fn.mass) / (self.total_mass + fn.mass)
        self.center_of_mass = [cx, cy]
        self.total_mass += fn.mass
        return inserted

    def subdivide(self):
        x_min, y_min, x_max, y_max = self.boundary
        x_mid = (x_min + x_max) / 2.0
        y_mid = (y_min + y_max) / 2.0

        self.children = [
            QuadNode((x_min, y_min, x_mid, y_mid)),  # Bottom-Left
            QuadNode((x_mid, y_min, x_max, y_mid)),  # Bottom-Right
            QuadNode((x_min, y_mid, x_mid, y_max)),  # Top-Left
            QuadNode((x_mid, y_mid, x_max, y_max))   # Top-Right
        ]


class QuantumScorer:
    def __init__(self, config: Config, indexer: Indexer):
        self.config = config
        self.indexer = indexer
        self.G = config.quantum_gravity_constant
        self.k_repulse = config.repulsive_constant
        self.dt = 0.05  # time step

    def gravitational_force(self, fi: FunctionNode, fj: FunctionNode, dist_semantic: float) -> float:
        """Attraction: F = G * (m_i * m_j) / d^2"""
        d = max(dist_semantic, 1e-5)
        return self.G * (fi.mass * fj.mass) / (d ** 2)

    def repulsive_force(self, fi: FunctionNode, fj: FunctionNode, dist_semantic: float) -> float:
        """Repulsion: R = k_repulse / d"""
        d = max(dist_semantic, 1e-5)
        return self.k_repulse / d

    def net_force(self, fi: FunctionNode, fj: FunctionNode, dist_semantic: float) -> float:
        return self.gravitational_force(fi, fj, dist_semantic) - self.repulsive_force(fi, fj, dist_semantic)

    def potential_energy(self, fi: FunctionNode, all_funcs: List[FunctionNode]) -> float:
        """U_i = - sum G * (m_i * m_j) / d_ij"""
        U = 0.0
        for fj in all_funcs:
            if fj.name == fi.name:
                continue
            d_sem = Embedder.semantic_distance(fi.embedding, fj.embedding)
            U -= self.G * (fi.mass * fj.mass) / max(d_sem, 1e-5)
        return U

    def cluster_centrality(self, fi: FunctionNode, cluster: List[FunctionNode]) -> float:
        """Distance of fi to the cluster mass-weighted center of mass."""
        total_mass = sum(f.mass for f in cluster)
        if total_mass == 0.0:
            return 0.0
        cx = sum(f.position[0] * f.mass for f in cluster) / total_mass
        cy = sum(f.position[1] * f.mass for f in cluster) / total_mass
        dist_to_centre = math.sqrt((fi.position[0] - cx)**2 + (fi.position[1] - cy)**2)
        return 1.0 / (1.0 + dist_to_centre)

    def compute_barnes_hut_forces(self, node: QuadNode, fn: FunctionNode, theta: float = 0.5) -> Tuple[float, float]:
        """Calculates 2D gravity + repulsion forces on a particle using Barnes-Hut."""
        if node.total_mass == 0.0:
            return 0.0, 0.0

        dx = node.center_of_mass[0] - fn.position[0]
        dy = node.center_of_mass[1] - fn.position[1]
        dist_2d = math.sqrt(dx**2 + dy**2)

        if node.children is None:
            # Leaf node
            if node.node is None or node.node.name == fn.name:
                return 0.0, 0.0
            dist_sem = Embedder.semantic_distance(fn.embedding, node.node.embedding)
            F = self.net_force(fn, node.node, dist_sem)
            dir_x = dx / max(dist_2d, 1e-5)
            dir_y = dy / max(dist_2d, 1e-5)
            return F * dir_x, F * dir_y

        # Internal node: evaluate theta
        x_min, _, x_max, _ = node.boundary
        width = x_max - x_min
        if width / max(dist_2d, 1e-5) < theta:
            dist_sem = min(dist_2d, 1.0)
            target = FunctionNode("com", fn.embedding)
            target.mass = node.total_mass
            F = self.net_force(fn, target, dist_sem)
            dir_x = dx / max(dist_2d, 1e-5)
            dir_y = dy / max(dist_2d, 1e-5)
            return F * dir_x, F * dir_y

        # Too close, traverse children
        fx, fy = 0.0, 0.0
        for child in node.children:
            cx, cy = self.compute_barnes_hut_forces(child, fn, theta)
            fx += cx
            fy += cy
        return fx, fy

    def run_simulation(self, functions: List[FunctionNode], iterations: int = 100):
        if not functions:
            return

        # Initialize positions
        for f in functions:
            f.position = [random.uniform(-1.0, 1.0), random.uniform(-1.0, 1.0)]
            f.velocity = [0.0, 0.0]

        n = len(functions)
        use_bh = n > 500

        for _ in range(iterations):
            if use_bh:
                # Build Quadtree
                xs = [f.position[0] for f in functions]
                ys = [f.position[1] for f in functions]
                x_min, x_max = min(xs) - 0.1, max(xs) + 0.1
                y_min, y_max = min(ys) - 0.1, max(ys) + 0.1
                root = QuadNode((x_min, y_min, x_max, y_max))
                for f in functions:
                    root.insert(f)

            for fi in functions:
                fx, fy = 0.0, 0.0
                if use_bh:
                    fx, fy = self.compute_barnes_hut_forces(root, fi)
                else:
                    for fj in functions:
                        if fi.name == fj.name:
                            continue
                        dist_sem = Embedder.semantic_distance(fi.embedding, fj.embedding)
                        F = self.net_force(fi, fj, dist_sem)
                        dx = fj.position[0] - fi.position[0]
                        dy = fj.position[1] - fi.position[1]
                        dist_2d = math.sqrt(dx**2 + dy**2)
                        fx += F * (dx / max(dist_2d, 1e-5))
                        fy += F * (dy / max(dist_2d, 1e-5))

                fi.velocity[0] = (fi.velocity[0] + fx * self.dt) * 0.9  # damping
                fi.velocity[1] = (fi.velocity[1] + fy * self.dt) * 0.9

            for fi in functions:
                fi.position[0] += fi.velocity[0] * self.dt
                fi.position[1] += fi.velocity[1] * self.dt

        # Post-simulation scoring (Vectorized for performance)
        import numpy as np
        try:
            embeddings = np.array([f.embedding for f in functions])
            masses = np.array([f.mass for f in functions])
            
            # Normalize embeddings to be safe
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1e-5
            norm_emb = embeddings / norms
            
            # Compute pairwise semantic distances (cosine distance)
            similarity = np.dot(norm_emb, norm_emb.T)
            d_sem = 1.0 - similarity
            d_sem = np.clip(d_sem, 1e-5, None)
            
            # Compute potential energy
            mass_products = np.outer(masses, masses)
            energy_matrix = -self.G * mass_products / d_sem
            np.fill_diagonal(energy_matrix, 0.0)
            pe_sums = np.sum(energy_matrix, axis=1)
            
            for idx, fi in enumerate(functions):
                fi.potential_energy = float(pe_sums[idx])
        except Exception:
            for fi in functions:
                fi.potential_energy = self.potential_energy(fi, functions)

        energies = [abs(f.potential_energy) for f in functions]
        max_energy = max(energies) if energies and max(energies) > 0 else 1.0

        for fi in functions:
            # Sigmoid normalisation
            u_norm = fi.potential_energy / max_energy
            pe_score = 1.0 - (1.0 / (1.0 + math.exp(-u_norm)))

            # Centrality
            cent_score = self.cluster_centrality(fi, functions)

            # Combined score
            fi.business_score = 0.7 * pe_score + 0.3 * cent_score

            # Technical Archetype Assignment (Replacing Quantum metaphors)
            if fi.business_score >= self.config.business_collapse_threshold:
                # High centrality and significant complexity in business context
                if cent_score > 0.6 and fi.mass > 2.5:
                    fi.quantum_state = "system-hub"
                else:
                    fi.quantum_state = "core-logic"
            elif fi.business_score <= 0.25:
                fi.quantum_state = "utility"
            else:
                fi.quantum_state = "standard-module"

    def write_physics_to_graph(self, functions: List[FunctionNode]):
        """
        Persist physical variables and quantum states to the internal mind (SQLite).
        Graph writes (SET/MERGE) are skipped as they are not supported by codebase-memory-mcp.
        """
        if not functions:
            return
            
        # 1. Update Internal Mind (SQLite) - This is our source of truth for computed physics
        for fi in functions:
            self.indexer.persistence.persist_physics(fi.name, fi.mass, fi.potential_energy, external=False)
            
            if fi.quantum_state:
                belief_state = {
                    "beliefs": {fi.quantum_state: 1.0},
                    "status": "ACTIVE",
                    "winner": fi.quantum_state,
                    "support_mass": fi.mass
                }
                self.indexer.persistence.persist_belief(fi.name, belief_state, external=False)
                
        logger.info(f"Persisted physics metadata for {len(functions)} symbols to the Internal Mind (SQLite).")
