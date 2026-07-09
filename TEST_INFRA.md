# E2E Test Infra: SentinelOps

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial Testing + Real-World Workload Testing.

## Feature Inventory
| # | Feature | Source (requirement) | Tier 1 | Tier 2 | Tier 3 |
|---|---------|---------------------|:------:|:------:|:------:|
| 1 | Alert Ingestion & Viewing | Follow-up — 2026-07-09T04:30:09Z R1 | 5 | 5 | ✓ |
| 2 | Investigation Reviewing | Follow-up — 2026-07-09T04:30:09Z R1 | 5 | 5 | ✓ |
| 3 | Confidence & Blast Radius | Follow-up — 2026-07-09T04:30:09Z R1 | 5 | 5 | ✓ |
| 4 | Plan Approval (HITL) | Follow-up — 2026-07-09T04:30:09Z R1 | 5 | 5 | ✓ |
| 5 | Plan Denial (HITL) | Follow-up — 2026-07-09T04:30:09Z R1 | 5 | 5 | ✓ |
| 6 | Timeout Auto-Denial | Follow-up — 2026-07-09T06:16:43Z R2 | 5 | 5 | ✓ |

## Test Architecture
- Test runner: Python virtual environment `.venv/bin/pytest`
- Invocation command: `bash scripts/run_e2e.sh`
- Test case format: pytest scripts targeting the FastAPI TestClient or server using standardized payloads and response models.
- Directory layout:
  - `tests/e2e/conftest.py` - Fixtures, database initialization/isolation, and LLM mock overrides.
  - `tests/e2e/test_tier1_connectivity.py` - Connectivity and basic auth verification.
  - `tests/e2e/test_tier2_single_incident.py` - Incident flows (approval/denial).
  - `tests/e2e/test_tier2_human_flow.py` - Detailed human operator flow and boundaries.
  - `tests/e2e/test_tier3_learning_loop.py` - Ingestion CSV, confidence learning, and suppression.
  - `tests/e2e/test_tier4_safety.py` - Safety controls, denylists, timeout fallback.
  - `tests/e2e/test_tier4_ui.py` - UI validation checks.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Normal Operator Shift | Ingestion, Reviewing, Confidence, Approval, Denial, Audit Logging | High |
| 2 | High Load Suppressed Flapping | Duplicate Ingestion, Suppression, Collapsing | Medium |
| 3 | Safety-Critical Denylist Rejection | Namespace validation, Denylist, Hard Rejection | Medium |
| 4 | Operator Timeout / Fallback Shift | Timeout Gating, Human Gating, State Isolation | High |
| 5 | Bayesian Confidence Ascent Loop | Ingestion, Training, Auto-Approval Threshold | High |

## Coverage Thresholds
- Tier 1: ≥5 per feature
- Tier 2: ≥5 per feature (where boundaries exist)
- Tier 3: pairwise coverage of major feature interactions
- Tier 4: ≥5 realistic application scenarios
