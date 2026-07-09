"""SQLite storage layer for SentinelOps.

Manages incidents, hypotheses, plans, fix_records, fix_outcomes, and graph_edges.
All CRUD operations are synchronous (SQLite is single-writer anyway).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sentinelops.models.incident import Hypothesis, Incident, Plan
from sentinelops.models.fix_record import FixOutcome, FixRecord


def _parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=__import__('datetime').timezone.utc)
    return dt


def _now_utc() -> datetime:
    return datetime.now(__import__('datetime').timezone.utc)

# Default DB path — overrideable for tests
DEFAULT_DB_PATH = Path("data/sentinelops.db")

# --- Schema ---
_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    resource TEXT NOT NULL,
    namespace TEXT NOT NULL,
    symptom_tags_json TEXT NOT NULL DEFAULT '[]',
    severity TEXT NOT NULL DEFAULT 'medium',
    raw_context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    provider TEXT NOT NULL DEFAULT 'mock',
    cluster_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    cause TEXT NOT NULL,
    p_diagnosis REAL NOT NULL DEFAULT 0.0,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL DEFAULT 0.0,
    blast_radius TEXT NOT NULL DEFAULT 'low',
    gate_decision TEXT NOT NULL DEFAULT 'pending',
    dry_run_diff TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS fix_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    symptom_cluster TEXT NOT NULL,
    prior_a REAL NOT NULL DEFAULT 2.0,
    prior_b REAL NOT NULL DEFAULT 2.0,
    UNIQUE(action, symptom_cluster)
);

CREATE TABLE IF NOT EXISTS fix_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fix_record_id INTEGER NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (fix_record_id) REFERENCES fix_records(id)
);

CREATE TABLE IF NOT EXISTS graph_edges (
    src_fingerprint TEXT NOT NULL,
    dst_fix_record_id INTEGER NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (src_fingerprint, dst_fix_record_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL,
    user TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_resource ON incidents(resource);
"""


class Store:
    """SQLite-backed persistence for SentinelOps state."""

    def __init__(self, db_path: Optional[Path | str] = None):
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        else:
            self.db_path = Path(db_path) if isinstance(db_path, str) else db_path

        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = __import__('threading').RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")
        self.conn.execute("PRAGMA cache_size=-8000;")
        self.conn.execute("PRAGMA temp_store=MEMORY;")
        self.conn.execute("PRAGMA mmap_size=268435456;")
        self.conn.execute("PRAGMA page_size=4096;")
        self._init_schema()

    def _init_schema(self):
        """Create tables if they don't exist."""
        with self._lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    def close(self):
        """Close the database connection."""
        with self._lock:
            self.conn.close()

    # --- Incident CRUD ---

    def create_incident(self, incident: Incident) -> int:
        """Insert a new incident and return its ID."""
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO incidents
                   (fingerprint, resource, namespace, symptom_tags_json,
                    severity, raw_context_json, created_at, status, provider, cluster_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    incident.fingerprint,
                    incident.resource,
                    incident.namespace,
                    json.dumps(incident.symptom_tags),
                    incident.severity,
                    json.dumps(incident.raw_context),
                    incident.created_at.isoformat(),
                    incident.status,
                    incident.provider,
                    incident.cluster_name,
                ),
            )
            self.conn.commit()
            incident.id = cur.lastrowid
            return cur.lastrowid

    def get_incident(self, incident_id: int) -> Optional[Incident]:
        """Retrieve an incident by ID."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def update_incident_status(self, incident_id: int, status: str):
        """Update the status of an incident."""
        with self._lock:
            self.conn.execute(
                "UPDATE incidents SET status = ? WHERE id = ?", (status, incident_id)
            )
            self.conn.commit()

    def list_incidents(self, status: Optional[str] = None) -> List[Incident]:
        """List incidents, optionally filtered by status."""
        with self._lock:
            if status:
                rows = self.conn.execute(
                    "SELECT * FROM incidents WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM incidents ORDER BY created_at DESC"
                ).fetchall()
            return [self._row_to_incident(r) for r in rows]

    def _row_to_incident(self, row: sqlite3.Row) -> Incident:
        return Incident(
            id=row["id"],
            fingerprint=row["fingerprint"],
            resource=row["resource"],
            namespace=row["namespace"],
            symptom_tags=json.loads(row["symptom_tags_json"]),
            severity=row["severity"],
            raw_context=json.loads(row["raw_context_json"]),
            created_at=_parse_dt(row["created_at"]),
            status=row["status"],
            provider=row["provider"],
            cluster_name=row["cluster_name"],
        )

    # --- Hypothesis CRUD ---

    def create_hypothesis(self, hyp: Hypothesis) -> int:
        """Insert a hypothesis and return its ID."""
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO hypotheses (incident_id, cause, p_diagnosis, evidence_json)
                   VALUES (?, ?, ?, ?)""",
                (hyp.incident_id, hyp.cause, hyp.p_diagnosis, json.dumps(hyp.evidence)),
            )
            self.conn.commit()
            hyp.id = cur.lastrowid
            return cur.lastrowid

    def get_hypotheses(self, incident_id: int) -> List[Hypothesis]:
        """Get all hypotheses for an incident."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM hypotheses WHERE incident_id = ?", (incident_id,)
            ).fetchall()
            return [
                Hypothesis(
                    id=r["id"],
                    incident_id=r["incident_id"],
                    cause=r["cause"],
                    p_diagnosis=r["p_diagnosis"],
                    evidence=json.loads(r["evidence_json"]),
                )
                for r in rows
            ]

    # --- Plan CRUD ---

    def create_plan(self, plan: Plan) -> int:
        """Insert a plan and return its ID."""
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO plans
                   (incident_id, action, params_json, confidence,
                    blast_radius, gate_decision, dry_run_diff)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    plan.incident_id,
                    plan.action,
                    json.dumps(plan.params),
                    plan.confidence,
                    plan.blast_radius,
                    plan.gate_decision,
                    plan.dry_run_diff,
                ),
            )
            self.conn.commit()
            plan.id = cur.lastrowid
            return cur.lastrowid

    def update_plan_gate(self, plan_id: int, gate_decision: str):
        """Update gate decision on a plan."""
        with self._lock:
            self.conn.execute(
                "UPDATE plans SET gate_decision = ? WHERE id = ?", (gate_decision, plan_id)
            )
            self.conn.commit()

    def get_plans(self, incident_id: int) -> List[Plan]:
        """Get all plans for an incident."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM plans WHERE incident_id = ?", (incident_id,)
            ).fetchall()
            return [
                Plan(
                    id=r["id"],
                    incident_id=r["incident_id"],
                    action=r["action"],
                    params=json.loads(r["params_json"]),
                    confidence=r["confidence"],
                    blast_radius=r["blast_radius"],
                    gate_decision=r["gate_decision"],
                    dry_run_diff=r["dry_run_diff"],
                )
                for r in rows
            ]

    # --- FixRecord CRUD ---

    def get_or_create_fix_record(self, action: str, symptom_cluster: str) -> FixRecord:
        """Get an existing fix record or create a new one."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM fix_records WHERE action = ? AND symptom_cluster = ?",
                (action, symptom_cluster),
            ).fetchone()
            if row:
                fr = FixRecord(
                    id=row["id"],
                    action=row["action"],
                    symptom_cluster=row["symptom_cluster"],
                    prior_a=row["prior_a"],
                    prior_b=row["prior_b"],
                )
                fr.outcomes = self._load_outcomes(fr.id)
                return fr

            cur = self.conn.execute(
                "INSERT INTO fix_records (action, symptom_cluster) VALUES (?, ?)",
                (action, symptom_cluster),
            )
            self.conn.commit()
            fr = FixRecord(id=cur.lastrowid, action=action, symptom_cluster=symptom_cluster)
            return fr

    def record_outcome(self, fix_record_id: int, success: bool, occurred_at: Optional[datetime] = None) -> FixOutcome:
        """Record a fix outcome for a fix record and update running priors."""
        ts = occurred_at or _now_utc()
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO fix_outcomes (fix_record_id, success, occurred_at) VALUES (?, ?, ?)",
                (fix_record_id, int(success), ts.isoformat()),
            )
            # Update running prior counts on the fix record
            self.conn.execute(
                "UPDATE fix_records SET prior_a = prior_a + ?, prior_b = prior_b + ? WHERE id = ?",
                (1.0 if success else 0.0, 0.0 if success else 1.0, fix_record_id),
            )
            self.conn.commit()
            return FixOutcome(id=cur.lastrowid, fix_record_id=fix_record_id, success=success, occurred_at=ts)

    def get_fix_record(self, fix_record_id: int) -> Optional[FixRecord]:
        """Get a fix record by ID with its outcomes loaded."""
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM fix_records WHERE id = ?", (fix_record_id,)
            ).fetchone()
            if not row:
                return None
            fr = FixRecord(
                id=row["id"],
                action=row["action"],
                symptom_cluster=row["symptom_cluster"],
                prior_a=row["prior_a"],
                prior_b=row["prior_b"],
            )
            fr.outcomes = self._load_outcomes(fr.id)
            return fr

    def list_fix_records(self) -> List[FixRecord]:
        """List all fix records with outcomes loaded."""
        with self._lock:
            rows = self.conn.execute("SELECT * FROM fix_records").fetchall()
            result = []
            for row in rows:
                fr = FixRecord(
                    id=row["id"],
                    action=row["action"],
                    symptom_cluster=row["symptom_cluster"],
                    prior_a=row["prior_a"],
                    prior_b=row["prior_b"],
                )
                fr.outcomes = self._load_outcomes(fr.id)
                result.append(fr)
            return result

    def bulk_upsert_graph_edges(self, edges: list[tuple[str, int, float]]):
        with self._lock:
            self.conn.executemany(
                """INSERT INTO graph_edges (src_fingerprint, dst_fix_record_id, weight)
                   VALUES (?, ?, ?)
                   ON CONFLICT(src_fingerprint, dst_fix_record_id)
                   DO UPDATE SET weight = weight + ?""",
                [(src, dst, w, w) for src, dst, w in edges],
            )
            self.conn.commit()

    def _load_outcomes(self, fix_record_id: int) -> List[FixOutcome]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM fix_outcomes WHERE fix_record_id = ? ORDER BY occurred_at",
                (fix_record_id,),
            ).fetchall()
            return [
                FixOutcome(
                    id=r["id"],
                    fix_record_id=r["fix_record_id"],
                    success=bool(r["success"]),
                    occurred_at=_parse_dt(r["occurred_at"]),
                )
                for r in rows
            ]

    # --- Graph Edge CRUD ---

    def upsert_graph_edge(self, src_fingerprint: str, dst_fix_record_id: int, weight: float = 1.0):
        """Insert or update a graph edge."""
        with self._lock:
            self.conn.execute(
                """INSERT INTO graph_edges (src_fingerprint, dst_fix_record_id, weight)
                   VALUES (?, ?, ?)
                   ON CONFLICT(src_fingerprint, dst_fix_record_id)
                   DO UPDATE SET weight = ?""",
                (src_fingerprint, dst_fix_record_id, weight, weight),
            )
            self.conn.commit()

    def get_graph_edges(self) -> List[dict]:
        """Get all graph edges as dicts."""
        with self._lock:
            rows = self.conn.execute("SELECT * FROM graph_edges").fetchall()
            return [
                {
                    "src_fingerprint": r["src_fingerprint"],
                    "dst_fix_record_id": r["dst_fix_record_id"],
                    "weight": r["weight"],
                }
                for r in rows
            ]

    # --- Audit Log CRUD ---

    def log_audit(self, action: str, details: dict, user: str = "system"):
        """Record an immutable audit log entry."""
        with self._lock:
            self.conn.execute(
                "INSERT INTO audit_logs (timestamp, action, details_json, user) VALUES (?, ?, ?, ?)",
                (_now_utc().isoformat(), action, json.dumps(details), user),
            )
            self.conn.commit()
