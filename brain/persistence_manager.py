import os
import sqlite3
import json
import time
from typing import Dict, Any, List, Optional
from brain.logger import get_logger

logger = get_logger(__name__)

class PersistenceManager:
    """
    Manages dual-persistence: 
    - External World (MCP Graph): Stable collapses and public symbols.
    - Internal Mind (SQLite): Private beliefs, lineage, and uncertainty.
    """
    def __init__(self, db_path: str, indexer):
        self.db_path = db_path
        self.indexer = indexer
        self.project_id = indexer._get_project_name()
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite sidecar for internal cognition."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Evidence Table (Lineage)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                project TEXT,
                id TEXT,
                fact TEXT,
                source TEXT,
                obs_type TEXT,
                scope TEXT,
                trust REAL,
                timestamp REAL,
                parent_id TEXT,
                status TEXT,
                inference_version TEXT,
                policy_version TEXT,
                PRIMARY KEY(project, id),
                FOREIGN KEY(project, parent_id) REFERENCES evidence(project, id)
            )
        """)
        
        # SAN Beliefs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS beliefs (
                project TEXT,
                symbol TEXT,
                belief_json TEXT,  -- Full probability distribution
                status TEXT,       -- ACTIVE, DORMANT, SUPERPOSITION
                winner TEXT,
                support_mass REAL,
                last_updated REAL,
                PRIMARY KEY(project, symbol)
            )
        """)
        
        # CEM Atoms Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS atoms (
                project TEXT,
                id TEXT,
                name TEXT,
                type TEXT,
                behavior_hash TEXT,
                flow_signature TEXT,
                data_json TEXT,
                PRIMARY KEY(project, id)
            )
        """)

        # Entanglements Table (Dependencies/Relations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entanglements (
                project TEXT,
                source TEXT,
                target TEXT,
                type TEXT,
                source_file TEXT,
                PRIMARY KEY(project, source, target, type)
            )
        """)
        
        conn.commit()
        conn.close()

    def persist_entanglement(self, source: str, target: str, ent_type: str, source_file: str):
        """Store structural/semantic bond in Internal Mind."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO entanglements 
            (project, source, target, type, source_file)
            VALUES (?, ?, ?, ?, ?)
        """, (self.project_id, source, target, ent_type, source_file))
        conn.commit()
        conn.close()

    def persist_observation(self, obs: Dict[str, Any]):
        """Store raw observation in the Internal Mind (SQLite)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO evidence 
            (project, id, fact, source, obs_type, scope, trust, timestamp, parent_id, status, inference_version, policy_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.project_id, obs["id"], obs["fact"], obs["source"], obs.get("type"), obs["scope"],
            obs["trust"], obs["timestamp"], obs.get("parent_id"), obs["status"],
            obs.get("inference_version"), obs.get("policy_version")
        ))
        conn.commit()
        conn.close()

    def persist_belief(self, symbol: str, state: Dict[str, Any], external: bool = False):
        """
        Store belief in Internal Mind (SQLite). 
        If external=True, also attempt to update the MCP Graph (External World).
        """
        # 1. Internal Write
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO beliefs 
            (project, symbol, belief_json, status, winner, support_mass, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            self.project_id, symbol, json.dumps(state["beliefs"]), state["status"], 
            state["winner"], state["support_mass"], time.time()
        ))
        conn.commit()
        conn.close()

        # 2. External Write (Best Effort)
        if external and state["status"] == "ACTIVE":
            try:
                # Map internal belief to external graph label
                query = (
                    f"MATCH (f:Function {{name: '{symbol}'}}) "
                    f"SET f.semantic_archetype = '{state['winner']}', "
                    f"    f.belief_confidence = {max(state['beliefs'].values())} "
                    f"RETURN f"
                )
                self.indexer.query_graph(query)
            except Exception as e:
                logger.debug(f"External graph update skipped for {symbol}: {e}")

    def persist_physics(self, symbol: str, mass: float, energy: float, external: bool = False):
        """Update physics metadata in both worlds."""
        if external:
            try:
                query = (
                    f"MATCH (f:Function {{name: '{symbol}'}}) "
                    f"SET f.mass = {mass}, f.potential_energy = {energy} "
                    f"RETURN f"
                )
                self.indexer.query_graph(query)
            except Exception as e:
                logger.debug(f"External physics update skipped for {symbol}: {e}")

    def get_internal_beliefs(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM beliefs WHERE project = ?", (self.project_id,))
        rows = cursor.fetchall()
        results = [dict(r) for r in rows]
        for r in results:
            r["beliefs"] = json.loads(r["belief_json"])
        conn.close()
        return results
