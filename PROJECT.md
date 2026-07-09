# Project: SentinelOps

## Architecture
SentinelOps is a confidence-driven autonomous incident remediation system.
- **Ingestion**: Listens for alerts and triggers (`IncidentSignal`) from major cloud providers (AWS, Azure, GCP, Alibaba) or simulates them.
- **Agents Pipeline**:
  - **Triage**: Categorizes the incoming signal and creates an `Incident`.
  - **Investigation**: Analyzes logs, metrics, or configuration and formulates hypotheses (`Hypothesis`).
  - **Planning**: Generates candidate playbooks (`Plan`) with computed confidence and dry-run outputs.
  - **Arbitration**: Evaluates confidence and blast radius against thresholds (`LOW_BLAST_BAR`, `PROD_AUTO_BAR`) to decide between auto-execution or human gate.
  - **Execution**: Runs the approved playbook action using the target cloud connector.
  - **Verification**: Assesses cluster state to confirm incident resolution and logs outcomes.
- **Memory Subsystem**: Uses SQLite for persistent storage of incidents, hypotheses, plans, and outcomes, alongside a NetworkX graph linking symptoms to successful actions. Calculates LCB (Lower Confidence Bound) using a Beta-Binomial posterior with time decay.
- **React Frontend**: Vite/React web dashboard displaying incident feeds, Bayesian confidence curves, and human approval queues.

## Code Layout
- `src/sentinelops/` — Python Backend
  - `main.py` — API server, entrypoint
  - `config/` — settings and environment
  - `models/` — SQLModel/Pydantic schemas
  - `connectors/` — cloud platform auth & interaction
  - `llm/` — Qwen OpenAI-compatible interface
  - `agents/` — multi-agent pipeline modules
  - `memory/` — SQLite store, graph, and LCB calculations
  - `playbooks/` — registered playbook actions
  - `gate/` — Telegram approval gate
  - `orchestrator.py` — pipeline orchestrator
- `frontend/` — React frontend dashboard
- `tests/` — unit and integration test suites

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | E2E Testing Track | Requirement-driven, opaque-box E2E test suite (Tiers 1-4) creating `TEST_READY.md` | None | IN_PROGRESS (cfcfbb1f-d080-44d8-b22c-bfdc7a19f099) |
| 2 | Implementation: Cloud Connectors | Flesh out AWS, GCP, Azure connectors, adding unit tests for 2 actions each | None | IN_PROGRESS (via 5db60bee-d089-4df9-ad41-dcd1cc104d80) |
| 3 | Implementation: Memory & SQLite | Memory profiling, database locking optimization, 1000 signals load test | None | IN_PROGRESS (via 5db60bee-d089-4df9-ad41-dcd1cc104d80) |
| 4 | Implementation: UI Polish | Network timeout handling, empty states, responsive viewports, no console errors | None | IN_PROGRESS (via 5db60bee-d089-4df9-ad41-dcd1cc104d80) |
| 5 | Implementation: Final E2E Integration | Wire A→I, pass 100% of E2E test suite, and run Tier 5 adversarial coverage hardening | M1, M2, M3, M4 | PLANNED |

## Interface Contracts
### Connectors ↔ Kubernetes Client
- Connectors expose `get_k8s_client(cluster_name: str) -> kubernetes.client.CoreV1Api` and `get_apps_client(cluster_name: str) -> kubernetes.client.AppsV1Api`
- Normalized `IncidentSignal` returned by connectors for ingestion.
