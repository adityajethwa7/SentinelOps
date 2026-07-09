"""NetworkX-based incident similarity graph.

Maps incident fingerprints to fix records via weighted edges.
Persisted to SQLite via the Store layer.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import List, Optional, Tuple
from threading import Lock

import networkx as nx

from sentinelops.memory.store import Store

DEFAULT_MAX_NODES = 10000
DEFAULT_TTL_SECONDS = 86400 * 30


class IncidentGraph:
    """In-memory graph linking incident fingerprints to fix records.

    Nodes:
      - Fingerprint nodes (prefixed 'fp:') — represent an incident pattern.
      - FixRecord nodes (prefixed 'fr:') — represent an (action, symptom_cluster) pair.

    Edges:
      - fp:X → fr:Y with weight = number of times this fix was used for this fingerprint.
    """

    def __init__(self, store: Optional[Store] = None, max_nodes: int = DEFAULT_MAX_NODES,
                 ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._lock = Lock()
        self.graph = nx.DiGraph()
        self.store = store
        self.max_nodes = max_nodes
        self.ttl_seconds = ttl_seconds
        self._node_timestamps: dict[str, float] = {}
        self._eviction_order: OrderedDict[str, None] = OrderedDict()
        if store:
            self._load_from_store()

    def _load_from_store(self):
        """Hydrate graph from SQLite graph_edges table."""
        with self._lock:
            edges = self.store.get_graph_edges()
            now = time.time()
            for edge in edges:
                fp_node = f"fp:{edge['src_fingerprint']}"
                fr_node = f"fr:{edge['dst_fix_record_id']}"
                self.graph.add_edge(fp_node, fr_node, weight=edge["weight"])
                self._node_timestamps.setdefault(fp_node, now)
                self._node_timestamps.setdefault(fr_node, now)

    def _prune_if_needed(self):
        """Evict oldest nodes when graph exceeds max_nodes."""
        if self.graph.number_of_nodes() <= self.max_nodes:
            return
        excess = self.graph.number_of_nodes() - self.max_nodes
        nodes = list(self.graph.nodes())
        nodes.sort(key=lambda n: self._node_timestamps.get(n, 0))
        for node in nodes[:excess]:
            self.graph.remove_node(node)
            self._node_timestamps.pop(node, None)

    def _prune_old_edges(self):
        """Remove edges older than TTL based on node timestamps."""
        with self._lock:
            now = time.time()
            stale = []
            for u, v in self.graph.edges():
                ts = max(
                    self._node_timestamps.get(u, 0),
                    self._node_timestamps.get(v, 0),
                )
                if now - ts > self.ttl_seconds:
                    stale.append((u, v))
            for u, v in stale:
                self.graph.remove_edge(u, v)
                if self.graph.degree(u) == 0:
                    self.graph.remove_node(u)
                    self._node_timestamps.pop(u, None)
                if self.graph.degree(v) == 0:
                    self.graph.remove_node(v)
                    self._node_timestamps.pop(v, None)

    def link(self, fingerprint: str, fix_record_id: int, weight: float = 1.0):
        """Create or update a link between a fingerprint and a fix record."""
        with self._lock:
            fp_node = f"fp:{fingerprint}"
            fr_node = f"fr:{fix_record_id}"
            now = time.time()

            if self.graph.has_edge(fp_node, fr_node):
                self.graph[fp_node][fr_node]["weight"] += weight
            else:
                self.graph.add_edge(fp_node, fr_node, weight=weight)

            self._node_timestamps[fp_node] = now
            self._node_timestamps[fr_node] = now
            self._eviction_order[fp_node] = None
            self._eviction_order.move_to_end(fp_node)
            self._eviction_order[fr_node] = None
            self._eviction_order.move_to_end(fr_node)

            new_weight = self.graph[fp_node][fr_node]["weight"]
            if self.store:
                self.store.upsert_graph_edge(fingerprint, fix_record_id, new_weight)

            self._prune_if_needed()
            self._prune_old_edges()

    def get_fix_records_for_fingerprint(self, fingerprint: str) -> List[Tuple[int, float]]:
        """Get fix record IDs and weights for a given fingerprint.

        Returns:
            List of (fix_record_id, weight) tuples sorted by weight descending.
        """
        with self._lock:
            fp_node = f"fp:{fingerprint}"
            if fp_node not in self.graph:
                return []

            neighbors = []
            for _, target, data in self.graph.edges(fp_node, data=True):
                fr_id = int(target.split(":")[1])
                neighbors.append((fr_id, data.get("weight", 1.0)))

            return sorted(neighbors, key=lambda x: x[1], reverse=True)

    def get_similar_fingerprints(self, fingerprint: str) -> List[str]:
        """Find fingerprints that share fix records with the given fingerprint.

        Uses the graph structure: fp1 → fr → fp2 means fp1 and fp2
        are similar (they share a fix pattern).
        """
        with self._lock:
            fp_node = f"fp:{fingerprint}"
            if fp_node not in self.graph:
                return []

            similar = set()
            for _, fr_node in self.graph.edges(fp_node):
                for pred_node in self.graph.predecessors(fr_node):
                    if pred_node != fp_node and pred_node.startswith("fp:"):
                        similar.add(pred_node[3:])

            return list(similar)

    @property
    def node_count(self) -> int:
        with self._lock:
            return self.graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        with self._lock:
            return self.graph.number_of_edges()
