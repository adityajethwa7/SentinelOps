# SentinelOps System Architecture

SentinelOps is a multi-agent autonomous remediation platform that strictly bounds AI behavior using Bayesian statistics and deterministic logic gates.

## Core Concepts

### 1. Multi-Agent Orchestrator
The `Orchestrator` coordinates a 4-stage pipeline:
- **Triage Agent (`triage.py`)**: Parses incoming alerts (JSON/webhook) to determine the exact failing resource and classify the symptoms.
- **Investigation Agent (`investigation.py`)**: Uses a mock/real LLM to identify the root cause of the parsed symptom. Crucially, it outputs a `diagnosis_confidence` score.
- **Planning Agent (`planning.py`)**: Reads the playbook catalog and proposes a concrete bash/python remediation action (e.g., `kubectl delete pod`).
- **Execution Agent (`execution.py`)**: Plugs into cloud connectors (AWS, GCP, Azure) to run the playbook action, observing the environment to verify if the fix actually succeeded.

### 2. The Bayesian Memory Graph
Located in `memory/confidence.py` and `memory/store.py`, SentinelOps implements a **Beta-Binomial Posterior** to track autonomous success mathematically.
- Every `(Resource, Symptom, Action)` tuple is stored.
- When an execution finishes, it counts as a `success` (adds to Beta Alpha) or `failure` (adds to Beta Beta).
- **Lower Confidence Bound (LCB)**: We never rely on the average success rate. We calculate the 10th percentile of the Beta distribution using optimized `scipy.stats.beta.ppf`. This ensures the system is severely distrustful of new actions with a small sample size.
- **Time Decay**: Observations decay exponentially over a 90-day half-life so stale outcomes don't permanently skew the system.

### 3. The Arbitration Gate
Before any action executes, it passes through the `ArbitrationGate`:
`Combined Confidence = Diagnosis Confidence * LCB Fix Probability`
If the Combined Confidence exceeds the predefined threshold (e.g., `0.90`), the action is executed autonomously. Otherwise, it halts in the `pending_human` state for manual approval.

### 4. Stack Topology
- **Backend:** `FastAPI` + `SQLite` (optimized with PRAGMA WAL and thread pools for high concurrency).
- **Frontend:** `Vite` + `React` (polling-safe hooks rendering live Bayesian confidence graphs via Recharts).
