"""FastAPI server exposing SentinelOps Orchestrator."""

import json
import csv
import io
import os
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from sentinelops.memory.store import Store
from sentinelops.memory.graph import IncidentGraph
from sentinelops.models.signal import IncidentSignal
from sentinelops.orchestrator import Orchestrator
from sentinelops.api.middleware import MemoryMonitorMiddleware, get_memory_stats
from sentinelops.config.settings import settings

API_KEY = os.environ.get("SENTINELOPS_API_KEY", "sentinelops-hackathon-2026")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    raise HTTPException(status_code=401, detail="Invalid or missing API Key")

# Global state
store = None
graph = None
orch = None

def get_store() -> Store:
    return store

def get_graph() -> IncidentGraph:
    return graph

def get_orch() -> Orchestrator:
    return orch

@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, graph, orch
    store = Store()
    graph = IncidentGraph(store)
    orch = Orchestrator(store, graph, provider=settings.CLOUD_PROVIDER, dry_run=True)
    yield
    store.close()

app = FastAPI(title="SentinelOps API", lifespan=lifespan)

# Must add before other middleware so CORS is applied first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(MemoryMonitorMiddleware, threshold_mb=150)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "sentinelops"}

@app.get("/api/status")
def api_status(store: Store = Depends(get_store), graph: IncidentGraph = Depends(get_graph)):
    incidents = store.list_incidents()
    stats = get_memory_stats(app)
    stats["active_incidents"] = len([i for i in incidents if i.status == "open"])
    stats["graph_nodes"] = graph.node_count if graph else 0
    stats["graph_edges"] = graph.edge_count if graph else 0
    return stats

class SignalInput(BaseModel):
    resource: str
    namespace: str
    raw_context: dict

@app.post("/api/signals")
def ingest_signal(signal_in: SignalInput, background_tasks: BackgroundTasks, api_key: str = Security(get_api_key), store: Store = Depends(get_store), orch: Orchestrator = Depends(get_orch)):
    # Validate payload size (e.g. limit raw_context size to 100KB)
    raw_context_size = len(json.dumps(signal_in.raw_context))
    if raw_context_size > 100000:
        raise HTTPException(status_code=413, detail="Payload too large")

    signal = IncidentSignal(
        resource=signal_in.resource,
        namespace=signal_in.namespace,
        raw_context=signal_in.raw_context
    )
    
    incident = orch.process_signal(signal)
    
    # Log audit for autonomous execution if it reached approved
    if incident.status == "resolved":
        store.log_audit("AUTONOMOUS_EXECUTION", {"incident_id": incident.id, "resource": signal.resource})
        
    return {"incident_id": incident.id, "status": incident.status}

@app.get("/api/incidents")
def list_incidents(store: Store = Depends(get_store)):
    # Intentionally open for the demo dashboard, no API key required for GET to make frontend easy
    incidents = store.list_incidents()
    result = []
    for inc in incidents:
        plans = store.get_plans(inc.id)
        inc_dict = inc.__dict__.copy()
        inc_dict["created_at"] = inc.created_at.isoformat()
        
        plan_list = []
        for p in plans:
            p_dict = p.__dict__.copy()
            plan_list.append(p_dict)
            
        inc_dict["plans"] = plan_list
        result.append(inc_dict)
    return result

@app.post("/api/plans/{plan_id}/approve")
def approve_plan(plan_id: int, api_key: str = Security(get_api_key), store: Store = Depends(get_store), orch: Orchestrator = Depends(get_orch)):
    row = store.conn.execute("SELECT incident_id FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")
        
    incident_id = row[0]
    incident = store.get_incident(incident_id)
    plans = store.get_plans(incident_id)
    plan = next((p for p in plans if p.id == plan_id), None)
    
    if plan.gate_decision != "pending_human":
        raise HTTPException(status_code=400, detail="Plan is not pending human approval")
        
    store.update_plan_gate(plan.id, "approved")
    # Simulate execution
    orch.execution.simulate_outcome(incident, plan, success=True)
    store.update_incident_status(incident.id, "resolved")
    
    # Immutable audit log
    store.log_audit("HUMAN_APPROVE", {"plan_id": plan.id, "action": plan.action, "incident_id": incident.id}, user="admin_ui")
    
    return {"status": "approved and executed"}

@app.post("/api/plans/{plan_id}/deny")
def deny_plan(plan_id: int, api_key: str = Security(get_api_key), store: Store = Depends(get_store)):
    row = store.conn.execute("SELECT incident_id FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Plan not found")
        
    incident_id = row[0]
    plans = store.get_plans(incident_id)
    plan = next((p for p in plans if p.id == plan_id), None)
    
    if not plan or plan.gate_decision != "pending_human":
        raise HTTPException(status_code=400, detail="Plan is not pending human approval/denial")
        
    store.update_plan_gate(plan_id, "denied")
    store.update_incident_status(incident_id, "open")
    
    store.log_audit("HUMAN_DENY", {"plan_id": plan_id, "incident_id": incident_id}, user="admin_ui")
    
    return {"status": "denied"}

@app.post("/api/ingest")
def ingest_historical_data(file: UploadFile = File(...), api_key: str = Security(get_api_key), store: Store = Depends(get_store), graph: IncidentGraph = Depends(get_graph)):
    """Ingest a CSV of historical data to train the Bayesian memory."""
    # Limit upload size to 1MB
    MAX_UPLOAD = 1_000_000
    contents = file.file.read(MAX_UPLOAD + 1)
    if len(contents) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="File too large")
    csv_str = contents.decode("utf-8")
    
    reader = csv.DictReader(io.StringIO(csv_str))
    success_count = 0
    
    try:
        for row in reader:
            resource = row['resource']
            symptom = row['symptom']
            action = row['action_taken']
            success = bool(int(row['success']))
            occurred_at = datetime.fromisoformat(row['timestamp'].replace("Z", ""))
            
            fr = store.get_or_create_fix_record(action, symptom)
            store.record_outcome(fr.id, success, occurred_at)
            fingerprint = f"{resource}-{symptom}"
            graph.link(fingerprint, fr.id, weight=1.0)
            success_count += 1
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing required CSV column: {e}")
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid value in CSV: {e}")
        
    store.log_audit("HISTORICAL_INGEST", {"rows_processed": success_count}, user="system")
    return {"status": "success", "rows_ingested": success_count}
